from freqtrade.strategy.interface import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd  # noqa

pd.options.mode.chained_assignment = None  # default='warn'
import technical.indicators as ftt
from functools import reduce

# Import hyperopt parameter types for strategy optimization
from freqtrade.strategy import CategoricalParameter, IntParameter, DecimalParameter


class IchiV1_Optimizable(IStrategy):
    """
    IchiV1 Optimizable Strategy - Ichimoku Cloud with Multi-Timeframe EMA Trend Analysis

    This strategy is an optimizable version of IchiV1_Fixed that allows hyperopt to find
    optimal parameter values for entry and exit conditions. It combines Ichimoku Cloud
    analysis with multiple Exponential Moving Averages (EMAs) across different timeframes
    to identify strong bullish trends and exit positions when price crosses below a
    specific EMA level.

    Optimizable Parameters:
    - buy_trend_above_senkou_level: Number of EMAs that must be above Ichimoku Cloud
    - buy_trend_bullish_level: Number of EMAs that must be bullish (close > open)
    - buy_fan_magnitude_shift_value: Number of previous candles to check for trend acceleration
    - buy_min_fan_magnitude_gain: Minimum fan magnitude gain threshold
    - sell_trend_indicator: EMA indicator used for exit signal (categorical choice)

    Entry Logic:
    - EMAs must be above Ichimoku Cloud (configurable level)
    - EMAs must be bullish (close > open) across multiple timeframes (configurable level)
    - Fan magnitude must be increasing (trend acceleration)
    - Fan magnitude must be greater than 1 (confirmed uptrend)

    Exit Logic:
    - Exit when price crosses below the selected EMA indicator (optimizable via hyperopt)
    """

    # Buy parameters - default values (will be overridden by hyperopt optimized values)
    buy_params = {
        "buy_trend_above_senkou_level": 1,
        "buy_trend_bullish_level": 6,
        "buy_fan_magnitude_shift_value": 3,
        "buy_min_fan_magnitude_gain": 1.002,
    }

    # Sell parameters - default value (will be updated with hyperopt optimization results)
    sell_params = {"sell_trend_indicator": "trend_close_30m"}

    # ============================================================
    # HYPEROPT SPACE - Optimizable Parameters for BUY Signals
    # ============================================================
    # These parameters define the search space for hyperopt optimization
    # during backtesting. Hyperopt will test different combinations to
    # find optimal values that maximize the selected objective function.

    buy_trend_above_senkou_level = IntParameter(
        1, 8, default=1, space="buy", optimize=True
    )
    # Number of EMAs that must be above Ichimoku Cloud (1-8)
    # Higher values require stronger trend confirmation (more EMAs above cloud)

    buy_trend_bullish_level = IntParameter(1, 8, default=6, space="buy", optimize=True)
    # Number of EMAs that must be bullish (close > open) across timeframes (1-8)
    # Higher values require more consistent bullish structure

    buy_fan_magnitude_shift_value = IntParameter(
        1, 10, default=3, space="buy", optimize=True
    )
    # Number of previous candles to verify increasing fan magnitude (1-10)
    # Higher values require more consistent trend acceleration

    buy_min_fan_magnitude_gain = DecimalParameter(
        1.001, 1.01, default=1.002, space="buy", optimize=True
    )
    # Minimum fan magnitude gain threshold (1.001 to 1.01)
    # Higher values require stronger trend acceleration (e.g., 1.002 = 0.2% minimum gain)

    # ============================================================
    # HYPEROPT SPACE - Optimizable Parameter for SELL Signals
    # ============================================================

    # Categorical parameter that hyperopt will optimize
    # This parameter determines which EMA indicator will be used as exit signal
    # Different EMAs provide different exit timing (faster = earlier exit, slower = later exit)
    sell_trend_indicator = CategoricalParameter(
        [
            "trend_close_5m",  # Fast EMA - exits very quickly (equivalent to current price)
            "trend_close_15m",  # Fast-medium EMA (EMA 3 periods) - quick exit
            "trend_close_30m",  # Medium EMA (EMA 6 periods) - balanced exit timing
            "trend_close_1h",  # Medium-slow EMA (EMA 12 periods) - later exit
            "trend_close_2h",  # Slow EMA (EMA 24 periods) - late exit
            "trend_close_4h",  # Very slow EMA (EMA 48 periods) - very late exit
            "trend_close_6h",  # Ultra slow EMA (EMA 72 periods) - extremely late exit
            "trend_close_8h",  # Maximum slow EMA (EMA 96 periods) - latest possible exit
        ],
        default="trend_close_30m",  # Default value if not optimized
        space="sell",  # Optimization space (sell signals)
        optimize=True,  # Enable optimization for this parameter
    )

    # ROI (Return on Investment) table - defines profit targets at different time intervals
    # Format: {time_in_minutes: profit_ratio}
    # Example: "0": 0.03 means take profit of 3% immediately, "10": 0.02 means 2% after 10 minutes
    minimal_roi = {"0": 0.03, "10": 0.02, "57": 0.01, "99": 0}

    # Stoploss - maximum loss percentage before exiting position
    stoploss = -0.275  # -27.5% stop loss

    # Strategy timeframe - base candle interval for analysis
    timeframe = "5m"

    # Number of candles required before strategy can start
    # Set to 96 to accommodate the longest EMA calculation (96 periods)
    startup_candle_count = 96

    # Process all historical candles or only new ones
    process_only_new_candles = False

    # Trailing stop configuration (currently disabled)
    trailing_stop = False

    # Exit signal configuration
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Plot configuration for freqtrade UI visualization
    # Defines how indicators are displayed in the strategy backtesting charts
    plot_config = {
        "main_plot": {
            "senkou_a": {
                "color": "green",
                "fill_to": "senkou_b",
                "fill_label": "Ichimoku Cloud",
                "fill_color": "rgba(255,76,46,0.2)",
            },
            "senkou_b": {},
            "trend_close_5m": {"color": "#FF5733"},  # Red
            "trend_close_15m": {"color": "#FF8333"},  # Orange-red
            "trend_close_30m": {"color": "#FFB533"},  # Orange
            "trend_close_1h": {"color": "#FFE633"},  # Yellow-orange
            "trend_close_2h": {"color": "#E3FF33"},  # Yellow-green
            "trend_close_4h": {"color": "#C4FF33"},  # Yellow-green
            "trend_close_6h": {"color": "#61FF33"},  # Yellow-green
            "trend_close_8h": {"color": "#33FF7D"},  # Green
        },
        "subplots": {
            "fan_magnitude": {"fan_magnitude": {}},
            "fan_magnitude_gain": {"fan_magnitude_gain": {}},
        },
    }

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Calculate all technical indicators required for the strategy.

        This method computes:
        - Heikin Ashi candles (smoothed price action)
        - Exponential Moving Averages (EMAs) for multiple timeframes
        - Fan magnitude indicators (trend strength measurement)
        - Ichimoku Cloud components
        - Average True Range (ATR) for volatility measurement

        Args:
            dataframe: DataFrame with OHLCV data
            metadata: Dictionary with pair metadata

        Returns:
            DataFrame with all calculated indicators added as columns
        """

        # Convert to Heikin Ashi candles to smooth price action and reduce noise
        # Heikin Ashi uses modified OHLC values based on previous candle
        heikinashi = qtpylib.heikinashi(dataframe)
        dataframe["open"] = heikinashi["open"]
        dataframe["high"] = heikinashi["high"]
        dataframe["low"] = heikinashi["low"]
        # Note: 'close' remains original price for accurate trend analysis

        # Calculate Exponential Moving Averages for closing prices across multiple timeframes
        # These EMAs represent trend strength at different temporal horizons
        # Naming convention: trend_close_Xm where X is the approximate timeframe
        dataframe["trend_close_5m"] = dataframe["close"]  # Current price (no smoothing)
        dataframe["trend_close_15m"] = ta.EMA(
            dataframe["close"], timeperiod=3
        )  # ~15 min equivalent
        dataframe["trend_close_30m"] = ta.EMA(
            dataframe["close"], timeperiod=6
        )  # ~30 min equivalent
        dataframe["trend_close_1h"] = ta.EMA(
            dataframe["close"], timeperiod=12
        )  # ~1 hour equivalent
        dataframe["trend_close_2h"] = ta.EMA(
            dataframe["close"], timeperiod=24
        )  # ~2 hours equivalent
        dataframe["trend_close_4h"] = ta.EMA(
            dataframe["close"], timeperiod=48
        )  # ~4 hours equivalent
        dataframe["trend_close_6h"] = ta.EMA(
            dataframe["close"], timeperiod=72
        )  # ~6 hours equivalent
        dataframe["trend_close_8h"] = ta.EMA(
            dataframe["close"], timeperiod=96
        )  # ~8 hours equivalent

        # Calculate Exponential Moving Averages for opening prices
        # Used to verify bullish trend (close > open) across multiple timeframes
        dataframe["trend_open_5m"] = dataframe["open"]
        dataframe["trend_open_15m"] = ta.EMA(dataframe["open"], timeperiod=3)
        dataframe["trend_open_30m"] = ta.EMA(dataframe["open"], timeperiod=6)
        dataframe["trend_open_1h"] = ta.EMA(dataframe["open"], timeperiod=12)
        dataframe["trend_open_2h"] = ta.EMA(dataframe["open"], timeperiod=24)
        dataframe["trend_open_4h"] = ta.EMA(dataframe["open"], timeperiod=48)
        dataframe["trend_open_6h"] = ta.EMA(dataframe["open"], timeperiod=72)
        dataframe["trend_open_8h"] = ta.EMA(dataframe["open"], timeperiod=96)

        # Fan Magnitude: Ratio between fast EMA (1h) and slow EMA (8h)
        # Values > 1 indicate bullish trend (fast EMA above slow EMA)
        # Values < 1 indicate bearish trend (fast EMA below slow EMA)
        # Higher values indicate stronger trend separation
        dataframe["fan_magnitude"] = (
            dataframe["trend_close_1h"] / dataframe["trend_close_8h"]
        )

        # Fan Magnitude Gain: Rate of change in fan magnitude
        # Measures trend acceleration/deceleration
        # Values > 1 indicate increasing trend strength (momentum building)
        # Values < 1 indicate decreasing trend strength (momentum weakening)
        dataframe["fan_magnitude_gain"] = dataframe["fan_magnitude"] / dataframe[
            "fan_magnitude"
        ].shift(1)

        # Calculate Ichimoku Cloud with custom parameters
        # Ichimoku Cloud provides support/resistance levels and trend direction
        ichimoku = ftt.ichimoku(
            dataframe,
            conversion_line_period=20,  # Tenkan-sen (conversion line)
            base_line_periods=60,  # Kijun-sen (base line)
            laggin_span=120,  # Chikou Span (lagging span)
            displacement=30,  # Cloud displacement (forward projection)
        )

        # Extract Ichimoku components
        # Note: Chikou Span is excluded to avoid lookahead bias (uses future data)
        dataframe["tenkan_sen"] = ichimoku[
            "tenkan_sen"
        ]  # Conversion line (fast moving average)
        dataframe["kijun_sen"] = ichimoku[
            "kijun_sen"
        ]  # Base line (slow moving average)
        dataframe["senkou_a"] = ichimoku[
            "senkou_span_a"
        ]  # Cloud span A (upper cloud boundary)
        dataframe["senkou_b"] = ichimoku[
            "senkou_span_b"
        ]  # Cloud span B (lower cloud boundary)
        dataframe["leading_senkou_span_a"] = ichimoku[
            "leading_senkou_span_a"
        ]  # Leading span A
        dataframe["leading_senkou_span_b"] = ichimoku[
            "leading_senkou_span_b"
        ]  # Leading span B
        dataframe["cloud_green"] = ichimoku[
            "cloud_green"
        ]  # Bullish cloud indicator (senkou_a > senkou_b)
        dataframe["cloud_red"] = ichimoku[
            "cloud_red"
        ]  # Bearish cloud indicator (senkou_a < senkou_b)

        # Average True Range (ATR) - measures market volatility
        # Can be used for dynamic stop loss or position sizing in future implementations
        dataframe["atr"] = ta.ATR(dataframe)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Define entry conditions for long positions.

        Entry signals are generated when ALL of the following conditions are met:
        1. EMAs are above Ichimoku Cloud (configurable via buy_trend_above_senkou_level)
        2. EMAs are bullish (close > open) across multiple timeframes (configurable via buy_trend_bullish_level)
        3. Fan magnitude is increasing (trend acceleration confirmed)
        4. Fan magnitude is greater than 1 (confirmed uptrend)

        All threshold parameters are optimizable via hyperopt.

        Args:
            dataframe: DataFrame with calculated indicators
            metadata: Dictionary with pair metadata

        Returns:
            DataFrame with 'enter_long' column set to 1 where conditions are met
        """

        conditions = []

        # ============================================================
        # CONDITION 1: EMAs Above Ichimoku Cloud
        # ============================================================
        # Verify that EMAs are positioned above both cloud boundaries (senkou_a and senkou_b)
        # Higher buy_trend_above_senkou_level.value requires more EMAs to be above the cloud
        # This ensures stronger trend confirmation by requiring multiple timeframe agreement
        # Parameter is optimizable via hyperopt (IntParameter: 1-8)

        if self.buy_trend_above_senkou_level.value >= 1:
            conditions.append(dataframe["trend_close_5m"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_5m"] > dataframe["senkou_b"])

        if self.buy_trend_above_senkou_level.value >= 2:
            conditions.append(dataframe["trend_close_15m"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_15m"] > dataframe["senkou_b"])

        if self.buy_trend_above_senkou_level.value >= 3:
            conditions.append(dataframe["trend_close_30m"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_30m"] > dataframe["senkou_b"])

        if self.buy_trend_above_senkou_level.value >= 4:
            conditions.append(dataframe["trend_close_1h"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_1h"] > dataframe["senkou_b"])

        if self.buy_trend_above_senkou_level.value >= 5:
            conditions.append(dataframe["trend_close_2h"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_2h"] > dataframe["senkou_b"])

        if self.buy_trend_above_senkou_level.value >= 6:
            conditions.append(dataframe["trend_close_4h"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_4h"] > dataframe["senkou_b"])

        if self.buy_trend_above_senkou_level.value >= 7:
            conditions.append(dataframe["trend_close_6h"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_6h"] > dataframe["senkou_b"])

        if self.buy_trend_above_senkou_level.value >= 8:
            conditions.append(dataframe["trend_close_8h"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_8h"] > dataframe["senkou_b"])

        # ============================================================
        # CONDITION 2: Bullish Trend Across Multiple Timeframes
        # ============================================================
        # Verify that Heikin Ashi candles are bullish (close > open) across timeframes
        # Higher buy_trend_bullish_level.value requires more EMAs to show bullish structure
        # This ensures consistent buying pressure across different time horizons
        # Parameter is optimizable via hyperopt (IntParameter: 1-8)

        if self.buy_trend_bullish_level.value >= 1:
            conditions.append(dataframe["trend_close_5m"] > dataframe["trend_open_5m"])

        if self.buy_trend_bullish_level.value >= 2:
            conditions.append(
                dataframe["trend_close_15m"] > dataframe["trend_open_15m"]
            )

        if self.buy_trend_bullish_level.value >= 3:
            conditions.append(
                dataframe["trend_close_30m"] > dataframe["trend_open_30m"]
            )

        if self.buy_trend_bullish_level.value >= 4:
            conditions.append(dataframe["trend_close_1h"] > dataframe["trend_open_1h"])

        if self.buy_trend_bullish_level.value >= 5:
            conditions.append(dataframe["trend_close_2h"] > dataframe["trend_open_2h"])

        if self.buy_trend_bullish_level.value >= 6:
            conditions.append(dataframe["trend_close_4h"] > dataframe["trend_open_4h"])

        if self.buy_trend_bullish_level.value >= 7:
            conditions.append(dataframe["trend_close_6h"] > dataframe["trend_open_6h"])

        if self.buy_trend_bullish_level.value >= 8:
            conditions.append(dataframe["trend_close_8h"] > dataframe["trend_open_8h"])

        # ============================================================
        # CONDITION 3: Fan Magnitude Analysis (Trend Acceleration)
        # ============================================================
        # Verify that trend momentum is increasing and confirmed
        # All parameters in this section are optimizable via hyperopt

        # Fan magnitude gain must exceed minimum threshold (e.g., 1.002 = 0.2% acceleration)
        # This ensures trend is accelerating, not just maintaining
        # Parameter is optimizable via hyperopt (DecimalParameter: 1.001-1.01)
        conditions.append(
            dataframe["fan_magnitude_gain"] >= self.buy_min_fan_magnitude_gain.value
        )

        # Fan magnitude must be greater than 1 (fast EMA above slow EMA)
        # This confirms overall uptrend structure
        conditions.append(dataframe["fan_magnitude"] > 1)

        # Verify fan magnitude has been increasing over N previous candles
        # This ensures consistent trend acceleration rather than isolated spikes
        # Parameter is optimizable via hyperopt (IntParameter: 1-10)
        for x in range(self.buy_fan_magnitude_shift_value.value):
            conditions.append(
                dataframe["fan_magnitude"].shift(x + 1) < dataframe["fan_magnitude"]
            )

        # ============================================================
        # ACTIVATE ENTRY SIGNAL
        # ============================================================
        # Set 'enter_long' to 1 where ALL conditions are simultaneously true
        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Define exit conditions for long positions.

        Exit signal is generated when:
        - Price (trend_close_5m) crosses below the selected EMA indicator

        The EMA indicator is determined by hyperopt optimization and can be any of the 8 options:
        - trend_close_5m (immediate exit, very aggressive)
        - trend_close_15m (fast exit)
        - trend_close_30m (medium exit timing)
        - trend_close_1h (medium-slow exit)
        - trend_close_2h (slow exit)
        - trend_close_4h (very slow exit)
        - trend_close_6h (ultra slow exit)
        - trend_close_8h (maximum slow exit, very conservative)

        The selection is optimizable via hyperopt using CategoricalParameter.

        Args:
            dataframe: DataFrame with calculated indicators
            metadata: Dictionary with pair metadata

        Returns:
            DataFrame with 'exit_long' column set to 1 where exit conditions are met
        """

        conditions = []

        # ============================================================
        # EXIT CONDITION: Price Crosses Below EMA
        # ============================================================
        # Exit when current price crosses below the configured EMA indicator
        # This indicates trend weakening or reversal
        # IMPORTANT: Use .value to access the value of the optimizable parameter
        # The EMA selection is optimized by hyperopt (CategoricalParameter)
        conditions.append(
            qtpylib.crossed_below(
                dataframe["trend_close_5m"],  # Current price (5m timeframe)
                dataframe[
                    self.sell_trend_indicator.value
                ],  # EMA selected by hyperopt optimization
            )
        )

        # ============================================================
        # ACTIVATE EXIT SIGNAL
        # ============================================================
        # Set 'exit_long' to 1 where exit condition is met
        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "exit_long"] = 1

        return dataframe

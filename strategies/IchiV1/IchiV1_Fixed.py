from freqtrade.strategy.interface import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd

pd.options.mode.chained_assignment = None
import technical.indicators as ftt
from functools import reduce
from datetime import datetime, timedelta
from freqtrade.strategy import merge_informative_pair
import numpy as np
from freqtrade.strategy import stoploss_from_open


class IchiV1_Fixed(IStrategy):
    """
    IchiV1 Fixed Strategy - Ichimoku Cloud with Multi-Timeframe EMA Trend Analysis

    This strategy combines Ichimoku Cloud analysis with multiple Exponential Moving Averages
    (EMAs) across different timeframes to identify strong bullish trends and exit positions
    when price crosses below a specific EMA level.

    Entry Logic:
    - EMAs must be above Ichimoku Cloud (strong trend confirmation)
    - EMAs must be bullish (close > open) across multiple timeframes
    - Fan magnitude must be increasing (trend acceleration)
    - Fan magnitude must be greater than 1 (confirmed uptrend)

    Exit Logic:
    - Exit when price crosses below the selected EMA indicator
    """

    # Buy signal parameters - optimized for more permissive entry conditions
    buy_params = {
        "buy_fan_magnitude_shift_value": 1,  # Number of previous candles to check for increasing fan magnitude
        "buy_min_fan_magnitude_gain": 1.001,  # Minimum fan magnitude gain threshold (0.1% acceleration)
        "buy_trend_above_senkou_level": 1,  # Minimum number of EMAs that must be above Ichimoku Cloud
        "buy_trend_bullish_level": 4,  # Minimum number of EMAs that must be bullish (close > open)
    }

    # Sell signal parameters
    sell_params = {
        "sell_trend_indicator": "trend_close_30m",  # EMA indicator used for exit signal
    }

    # ROI (Return on Investment) table - defines profit targets at different time intervals
    # Format: {time_in_minutes: profit_ratio}
    minimal_roi = {"0": 0.03, "10": 0.02, "57": 0.01, "99": 0}

    # Stoploss - maximum loss percentage before exiting position
    stoploss = -0.275  # -27.5%

    # Strategy timeframe - base candle interval for analysis
    timeframe = "5m"

    # Number of candles required before strategy can start (needed for longest EMA calculation)
    startup_candle_count = 96

    # Process all historical candles or only new ones
    process_only_new_candles = False

    # Trailing stop configuration (currently disabled)
    trailing_stop = False
    # trailing_stop_positive = 0.002
    # trailing_stop_positive_offset = 0.025
    # trailing_only_offset_is_reached = True

    # Exit signal configuration
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Plot configuration for freqtrade UI visualization
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

    def populate_indicators(self, dataframe: DataFrame) -> DataFrame:
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
        # dataframe['chikou_span'] = ichimoku['chikou_span']  # Excluded - causes lookahead bias

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

    def populate_entry_trend(self, dataframe: DataFrame) -> DataFrame:
        """
        Define entry conditions for long positions.

        Entry signals are generated when ALL of the following conditions are met:
        1. EMAs are above Ichimoku Cloud (strong trend confirmation)
        2. EMAs are bullish (close > open) across multiple timeframes
        3. Fan magnitude is increasing (trend acceleration confirmed)
        4. Fan magnitude is greater than 1 (confirmed uptrend)

        Args:
            dataframe: DataFrame with calculated indicators

        Returns:
            DataFrame with 'enter_long' column set to 1 where conditions are met
        """

        conditions = []

        # ============================================================
        # CONDITION 1: EMAs Above Ichimoku Cloud
        # ============================================================
        # Verify that EMAs are positioned above both cloud boundaries (senkou_a and senkou_b)
        # Higher buy_trend_above_senkou_level requires more EMAs to be above the cloud
        # This ensures stronger trend confirmation by requiring multiple timeframe agreement

        if self.buy_params["buy_trend_above_senkou_level"] >= 1:
            conditions.append(dataframe["trend_close_5m"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_5m"] > dataframe["senkou_b"])

        if self.buy_params["buy_trend_above_senkou_level"] >= 2:
            conditions.append(dataframe["trend_close_15m"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_15m"] > dataframe["senkou_b"])

        if self.buy_params["buy_trend_above_senkou_level"] >= 3:
            conditions.append(dataframe["trend_close_30m"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_30m"] > dataframe["senkou_b"])

        if self.buy_params["buy_trend_above_senkou_level"] >= 4:
            conditions.append(dataframe["trend_close_1h"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_1h"] > dataframe["senkou_b"])

        if self.buy_params["buy_trend_above_senkou_level"] >= 5:
            conditions.append(dataframe["trend_close_2h"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_2h"] > dataframe["senkou_b"])

        if self.buy_params["buy_trend_above_senkou_level"] >= 6:
            conditions.append(dataframe["trend_close_4h"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_4h"] > dataframe["senkou_b"])

        if self.buy_params["buy_trend_above_senkou_level"] >= 7:
            conditions.append(dataframe["trend_close_6h"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_6h"] > dataframe["senkou_b"])

        if self.buy_params["buy_trend_above_senkou_level"] >= 8:
            conditions.append(dataframe["trend_close_8h"] > dataframe["senkou_a"])
            conditions.append(dataframe["trend_close_8h"] > dataframe["senkou_b"])

        # ============================================================
        # CONDITION 2: Bullish Trend Across Multiple Timeframes
        # ============================================================
        # Verify that Heikin Ashi candles are bullish (close > open) across timeframes
        # Higher buy_trend_bullish_level requires more EMAs to show bullish structure
        # This ensures consistent buying pressure across different time horizons

        if self.buy_params["buy_trend_bullish_level"] >= 1:
            conditions.append(dataframe["trend_close_5m"] > dataframe["trend_open_5m"])

        if self.buy_params["buy_trend_bullish_level"] >= 2:
            conditions.append(
                dataframe["trend_close_15m"] > dataframe["trend_open_15m"]
            )

        if self.buy_params["buy_trend_bullish_level"] >= 3:
            conditions.append(
                dataframe["trend_close_30m"] > dataframe["trend_open_30m"]
            )

        if self.buy_params["buy_trend_bullish_level"] >= 4:
            conditions.append(dataframe["trend_close_1h"] > dataframe["trend_open_1h"])

        if self.buy_params["buy_trend_bullish_level"] >= 5:
            conditions.append(dataframe["trend_close_2h"] > dataframe["trend_open_2h"])

        if self.buy_params["buy_trend_bullish_level"] >= 6:
            conditions.append(dataframe["trend_close_4h"] > dataframe["trend_open_4h"])

        if self.buy_params["buy_trend_bullish_level"] >= 7:
            conditions.append(dataframe["trend_close_6h"] > dataframe["trend_open_6h"])

        if self.buy_params["buy_trend_bullish_level"] >= 8:
            conditions.append(dataframe["trend_close_8h"] > dataframe["trend_open_8h"])

        # ============================================================
        # CONDITION 3: Fan Magnitude Analysis (Trend Acceleration)
        # ============================================================
        # Verify that trend momentum is increasing and confirmed

        # Fan magnitude gain must exceed minimum threshold (e.g., 1.001 = 0.1% acceleration)
        # This ensures trend is accelerating, not just maintaining
        conditions.append(
            dataframe["fan_magnitude_gain"]
            >= self.buy_params["buy_min_fan_magnitude_gain"]
        )

        # Fan magnitude must be greater than 1 (fast EMA above slow EMA)
        # This confirms overall uptrend structure
        conditions.append(dataframe["fan_magnitude"] > 1)

        # Verify fan magnitude has been increasing over N previous candles
        # This ensures consistent trend acceleration rather than isolated spikes
        for x in range(self.buy_params["buy_fan_magnitude_shift_value"]):
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

    def populate_exit_trend(self, dataframe: DataFrame) -> DataFrame:
        """
        Define exit conditions for long positions.

        Exit signal is generated when:
        - Price (trend_close_5m) crosses below the selected EMA indicator

        The EMA indicator is configured via sell_params["sell_trend_indicator"] and can be
        any of the calculated trend_close_Xm indicators. Faster EMAs (e.g., trend_close_15m)
        provide earlier exits, while slower EMAs (e.g., trend_close_8h) provide later exits.

        Args:
            dataframe: DataFrame with calculated indicators

        Returns:
            DataFrame with 'exit_long' column set to 1 where exit conditions are met
        """

        conditions = []

        # ============================================================
        # EXIT CONDITION: Price Crosses Below EMA
        # ============================================================
        # Exit when current price crosses below the configured EMA indicator
        # This indicates trend weakening or reversal
        conditions.append(
            qtpylib.crossed_below(
                dataframe["trend_close_5m"],  # Current price (5m timeframe)
                dataframe[
                    self.sell_params["sell_trend_indicator"]
                ],  # Selected EMA indicator
            )
        )

        # ============================================================
        # ACTIVATE EXIT SIGNAL
        # ============================================================
        # Set 'exit_long' to 1 where exit condition is met
        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "exit_long"] = 1

        return dataframe

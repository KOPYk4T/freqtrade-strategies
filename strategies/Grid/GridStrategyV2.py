from freqtrade.strategy.interface import IStrategy
from typing import Dict, List, Optional
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
from pandas import DataFrame

class GridStrategyV2(IStrategy):
    """
    Grid Trading - Stop loss ampliado para soportar volatilidad cripto
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    
    # ROI escalonado
    minimal_roi = {
        "0": 0.025,
        "60": 0.015,
        "180": 0.01
    }
    
    # Stop loss AMPLIADO de 3% a 6%
    stoploss = -0.06
    
    # Trailing stop para proteger ganancias
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.015
    trailing_only_offset_is_reached = True
    
    grid_spacing_percent = 2.0
    grid_levels = 4
    
    exit_profit_only = True
    use_exit_signal = True
    can_short = False
    startup_candle_count: int = 30
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volumen
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Compra más agresiva - RSI < 30 en lugar de < 35
        """
        dataframe.loc[
            (
                (dataframe['close'] <= dataframe['bb_lowerband']) |
                (dataframe['rsi'] < 30)
            ) &
            (dataframe['volume'] > 0),
            'enter_long'
        ] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Venta solo cuando está claramente alto
        """
        dataframe.loc[
            (
                (dataframe['close'] >= dataframe['bb_upperband']) &
                (dataframe['rsi'] > 70)
            ) &
            (dataframe['volume'] > 0),
            'exit_long'
        ] = 1
        
        return dataframe
from freqtrade.strategy.interface import IStrategy
from typing import Dict, List, Optional
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
from pandas import DataFrame

class GridStrategy(IStrategy):
    """
    Estrategia de Grid Trading optimizada para $100
    - Compra en niveles bajos
    - Vende en niveles altos  
    - Mantiene rejilla dinámica
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    
    # ROI y Stoploss
    minimal_roi = {
        "0": 0.02  # 2% ganancia por trade
    }
    
    stoploss = -0.05  # 5% stop loss máximo
    
    # Grid Settings - AJUSTABLES
    grid_spacing_percent = 2.0    # 2% entre niveles
    grid_levels = 4               # 4 niveles arriba/abajo
    
    # Configuración adicional
    can_short = False
    startup_candle_count: int = 30
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Añadir indicadores técnicos para Grid Trading
        """
        
        # SMA para determinar tendencia general
        dataframe['sma_20'] = ta.SMA(dataframe, timeperiod=20)
        dataframe['sma_50'] = ta.SMA(dataframe, timeperiod=50)
        
        # RSI para evitar comprar en sobrecompra
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # ATR para medir volatilidad
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Bollinger Bands para límites de grid
        bollinger = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        
        # Calcular niveles de grid dinámicos
        dataframe['grid_buy_level'] = dataframe['close'] * (1 - self.grid_spacing_percent / 100)
        dataframe['grid_sell_level'] = dataframe['close'] * (1 + self.grid_spacing_percent / 100)
        
        # Volumen promedio
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Condiciones de compra para Grid Trading
        """
        
        dataframe.loc[
            (
                # Grid Buy Conditions
                (dataframe['close'] <= dataframe['bb_lowerband']) |  # Precio en banda inferior
                (dataframe['rsi'] < 40) |                            # RSI indica sobreventa
                (
                    (dataframe['close'] < dataframe['sma_20']) &     # Precio bajo SMA
                    (dataframe['volume'] > dataframe['volume_sma'])   # Volumen alto
                )
            ) &
            (dataframe['volume'] > 0) &                              # Volumen mínimo
            (dataframe['close'] > 0),                                # Precio válido
            'enter_long'
        ] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Condiciones de venta para Grid Trading
        """
        
        dataframe.loc[
            (
                # Grid Sell Conditions
                (dataframe['close'] >= dataframe['bb_upperband']) |  # Precio en banda superior
                (dataframe['rsi'] > 60) |                            # RSI indica sobrecompra
                (
                    (dataframe['close'] > dataframe['sma_20']) &     # Precio sobre SMA
                    (dataframe['volume'] > dataframe['volume_sma'])   # Volumen alto
                )
            ) &
            (dataframe['volume'] > 0),                               # Volumen mínimo
            'exit_long'
        ] = 1
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time, current_rate,
                       current_profit: float, **kwargs) -> float:
        """
        Stop loss dinámico para Grid Trading
        """
        
        # Si estamos ganando más del 1%, ajustar stop loss
        if current_profit > 0.01:
            return -0.02  # Stop loss a -2% si ya ganamos 1%
        
        # Stop loss normal
        return self.stoploss
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                           rate: float, time_in_force: str, current_time,
                           entry_tag, side: str, **kwargs) -> bool:
        """
        Confirmar entrada de trade - útil para validaciones extra
        """
        
        # Lógica adicional si es necesaria
        # Por ejemplo, no entrar si ya tenemos muchas posiciones del mismo par
        
        return True
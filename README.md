# Freqtrade Strategies

Colección de estrategias de trading algorítmico para Freqtrade, diseñadas para diferentes estilos de trading y condiciones de mercado.

## Estrategias Disponibles

### IchiV1 - Ichimoku Cloud Multi-Timeframe

Estrategia basada en análisis de Ichimoku Cloud combinado con múltiples EMAs (Exponential Moving Averages) para detectar tendencias fuertes y entradas en momentum alcista.

#### Versiones Disponibles:

**IchiV1_Fixed**

- Versión con parámetros fijos optimizados manualmente
- Parámetros de entrada más permisivos para mayor frecuencia de señales
- Optimización de señales de salida basada en EMA cruzada

**IchiV1_Optimizable**

- Versión preparada para optimización con Hyperopt
- Parámetros optimizables:
  - `buy_trend_above_senkou_level`: Número de EMAs que deben estar sobre la nube Ichimoku (1-8)
  - `buy_trend_bullish_level`: Número de EMAs que deben ser alcistas (1-8)
  - `buy_fan_magnitude_shift_value`: Candles previos para verificar aceleración (1-10)
  - `buy_min_fan_magnitude_gain`: Umbral mínimo de ganancia de fan magnitude (1.001-1.01)
  - `sell_trend_indicator`: EMA seleccionada para señal de salida (categórico)

**Características:**

- **Timeframe**: 5m
- **Indicadores**: Ichimoku Cloud, EMAs múltiples (5m a 8h), Fan Magnitude
- **Stoploss**: -27.5%
- **ROI**: Escalonado (3% → 2% → 1% → 0%)
- **Startup candles**: 96

**Lógica de Entrada:**

1. EMAs deben estar por encima de Ichimoku Cloud (tendencia fuerte)
2. EMAs deben ser alcistas (close > open) en múltiples timeframes
3. Fan magnitude debe estar creciendo (aceleración de tendencia)
4. Fan magnitude > 1 (confirmación de uptrend)

**Lógica de Salida:**

- Salida cuando precio cruza por debajo de la EMA seleccionada

---

### E0V1E - RSI Multi-Timeframe con Custom Stoploss

Estrategia basada en indicadores RSI (Relative Strength Index) en múltiples períodos, combinada con SMA (Simple Moving Average) y CTI (Correlation Trend Indicator) para identificar entradas en condiciones de sobreventa.

**Características:**

- **Timeframe**: 5m
- **Indicadores**: RSI (múltiples períodos), SMA 15, CTI
- **Stoploss**: -25% (base)
- **Custom Stoploss**:
  - -0.2% si profit >= 5%
  - -0.3% si profit >= 3% y tag es "buy_new"
- **Trailing Stop**: Habilitado (0.2% después de 5% de ganancia)
- **Startup candles**: 240
- **Protection**: Cooldown period de 18 candles

**Parámetros Optimizables:**

- `buy_rsi_fast_32`: RSI rápido (20-70)
- `buy_rsi_32`: RSI principal (15-50)
- `buy_sma15_32`: Ratio SMA 15 (0.900-1.000)
- `buy_cti_32`: Correlation Trend Indicator (-1 a 1)
- `sell_fastx`: Umbral de RSI para venta (50-100)
- `buy_rsi_period`: Período RSI principal (10-190)
- `buy_rsi_fast_period`: Período RSI rápido (10-190)
- `buy_rsi_slow_period`: Período RSI lento (10-190)
- `buy_sma_period`: Período SMA (10-190)

**Archivos:**

- `E0V1E.py`: Versión principal
- `E0V1E_opti.py`: Versión optimizable con Hyperopt
- `E0V1E.json`: Parámetros optimizados

---

### Grid Trading - Estrategias de Rejilla

Estrategias de Grid Trading que operan comprando en niveles bajos y vendiendo en niveles altos, aprovechando la volatilidad del mercado mediante una rejilla de precios dinámica.

#### GridStrategy

Versión base de Grid Trading con stop loss conservador.

**Características:**

- **Timeframe**: 5m
- **Indicadores**: Bollinger Bands, RSI, SMA 20/50, ATR, Volume SMA
- **Stoploss**: -5%
- **ROI**: 2% por trade
- **Grid spacing**: 2% entre niveles
- **Grid levels**: 4 niveles arriba/abajo

**Lógica de Entrada:**

- Precio en banda inferior de Bollinger
- RSI < 40 (sobreventa)
- Precio bajo SMA 20 con volumen alto

**Lógica de Salida:**

- Precio en banda superior de Bollinger
- RSI > 60 (sobrecompra)
- Precio sobre SMA 20

#### GridStrategyV2

Versión mejorada con stop loss ampliado y trailing stop para mayor protección de ganancias.

**Mejoras sobre GridStrategy:**

- **Stoploss ampliado**: -6% (mejor para volatilidad alta)
- **Trailing stop**: Habilitado (1% después de 1.5% de ganancia)
- **ROI escalonado**: 2.5% → 1.5% → 1%
- **Entrada más agresiva**: RSI < 30 (en lugar de < 40)
- **Salida más conservadora**: Requiere RSI > 70 y precio en banda superior

**Características:**

- **Timeframe**: 5m
- **Indicadores**: Bollinger Bands, RSI, Volume SMA
- **Exit profit only**: Solo vende en ganancias

---

## 🚀 Instalación

### 1. Prerequisitos

Asegúrate de tener Python 3.8+ y Freqtrade instalado:

```bash
pip install freqtrade pandas talib-binary technical pandas-ta
```

### 2. Copiar Estrategias

Copia las estrategias a tu carpeta `user_data/strategies/`:

```bash
# Opción 1: Copiar todas las estrategias
cp -r strategies/* /ruta/a/freqtrade/user_data/strategies/

# Opción 2: Copiar estrategia específica
cp strategies/IchiV1/IchiV1_Fixed.py /ruta/a/freqtrade/user_data/strategies/
```

### 3. Estructura de Archivos

```
user_data/strategies/
├── IchiV1/
│   ├── IchiV1_Fixed.py
│   ├── IchiV1_Optimizable.py
│   └── IchiV1_Optimizable.json
├── E0V1E/
│   ├── E0V1E.py
│   ├── E0V1E_opti.py
│   └── E0V1E.json
└── Grid/
    ├── GridStrategy.py
    └── GridStrategyV2.py
```

---

## Uso

### Backtesting

```bash
# IchiV1
freqtrade backtesting --strategy IchiV1_Fixed --timerange 20240101-20241201

# E0V1E
freqtrade backtesting --strategy E0V1E --timerange 20240101-20241201

# Grid Trading
freqtrade backtesting --strategy GridStrategy --timerange 20240101-20241201
```

### Dry Run (Prueba en Vivo sin Dinero Real)

```bash
# IchiV1
freqtrade trade --strategy IchiV1_Fixed --dry-run

# E0V1E
freqtrade trade --strategy E0V1E --dry-run

# Grid Trading
freqtrade trade --strategy GridStrategyV2 --dry-run
```

### Optimización con Hyperopt

```bash
# IchiV1 Optimizable
freqtrade hyperopt \
    --strategy IchiV1_Optimizable \
    --hyperopt-loss SharpeHyperOptLoss \
    --epochs 100 \
    --timerange 20240101-20241201

# E0V1E Optimizable
freqtrade hyperopt \
    --strategy E0V1E_opti \
    --hyperopt-loss SharpeHyperOptLoss \
    --epochs 100 \
    --timerange 20240101-20241201
```

---

## ⚙️ Configuración Recomendada

### Para IchiV1

- **Max open trades**: 3-6
- **Stake amount**: 25-50 USDT
- **Stoploss**: -27.5% (ajustable según perfil de riesgo)
- **Timeframe**: 5m
- **Trading pairs**: Mayormente altcoins con buena liquidez

### Para E0V1E

- **Max open trades**: 5-10
- **Stake amount**: 20-40 USDT
- **Stoploss**: -25% (base, con custom stoploss dinámico)
- **Timeframe**: 5m
- **Trading pairs**: Pairs con volatilidad media-alta

### Para Grid Trading

- **Max open trades**: 3-5
- **Stake amount**: 30-60 USDT
- **Stoploss**: -5% a -6% según versión
- **Timeframe**: 5m
- **Trading pairs**: Pairs con alta volatilidad y rango lateral

---

## 📚 Recursos Adicionales

- [Documentación de Freqtrade](https://www.freqtrade.io/)
- [Hyperopt Optimization Guide](https://www.freqtrade.io/en/stable/hyperopt/)
- [Risk Management Best Practices](https://www.freqtrade.io/en/stable/risk-management/)

---

**Disclaimer**: Este software es solo para fines educativos. El trading de criptomonedas conlleva riesgos significativos y puede resultar en pérdidas de capital. Usa bajo tu propia responsabilidad. El autor no se hace responsable de las pérdidas financieras derivadas del uso de estas estrategias.

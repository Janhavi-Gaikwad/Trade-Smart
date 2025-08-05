import pandas as pd
import plotly.graph_objs as go
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import os

# ---- Config ----
DATA_FOLDER = r"D:\intellij project\Project_data\simulation_price_data_July_1-Aug_30"
VISIBLE_ROWS = 100

# ---- Dataset options ----
DATASETS = {
    "AAPL": "simulated_AAPL_live.csv",
    "TSLA": "simulated_TSLA_live.csv",
    "GOOG": "simulated_GOOG_live.csv",
    "MSFT": "simulated_MSFT_live.csv",
    "UL": "simulated_UL_live.csv",
    "IBM": "simulated_IBM_live.csv",
    "WMT": "simulated_WMT_live.csv"
}

# ---- Helper Function ----
def load_data(ticker):
    file_path = os.path.join(DATA_FOLDER, DATASETS[ticker])
    df = pd.read_csv(file_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

# ---- Dash App Init ----
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Multi-Stock Live Candlestick Chart"

# ---- Layout ----
app.layout = html.Div([
    html.H2("Live Candlestick Chart Viewer", className="text-center mt-4"),

    dbc.Row([
        dbc.Col([
            html.Label("Select Stock:"),
            dcc.Dropdown(
                id="stock-selector",
                options=[{"label": k, "value": k} for k in DATASETS.keys()],
                value="AAPL",
                clearable=False,
                style={"width": "200px"}
            )
        ]),
        dbc.Col(dbc.Checklist(
            options=[
                {"label": "RSI", "value": "RSI"},
                {"label": "MACD", "value": "MACD"},
                {"label": "Volume", "value": "Volume"}
            ],
            value=["Volume"],
            id="indicators-toggle",
            inline=True,
            switch=True
        ))
    ], className="mb-3 justify-content-center"),

    dcc.Graph(id="candlestick-chart", config={"displayModeBar": False}),
    dcc.Interval(id="interval-update", interval=1000, n_intervals=0),
])

# ---- Callback ----
@app.callback(
    Output("candlestick-chart", "figure"),
    Input("interval-update", "n_intervals"),
    Input("stock-selector", "value"),
    Input("indicators-toggle", "value")
)
def update_chart(n, stock, indicators):
    df = load_data(stock)
    end = min(VISIBLE_ROWS + n, len(df))
    data = df.iloc[:end]

    fig = go.Figure()

    # ---- Candlestick
    fig.add_trace(go.Candlestick(
        x=data['timestamp'],
        open=data['open'],
        high=data['high'],
        low=data['low'],
        close=data['close'],
        name='Candlestick'
    ))

    # ---- Volume
    if "Volume" in indicators:
        fig.add_trace(go.Bar(
            x=data['timestamp'],
            y=data['volume'],
            name='Volume',
            marker_color='lightblue',
            yaxis='y2'
        ))

    # ---- RSI
    if "RSI" in indicators and len(data) >= 15:
        delta = data['close'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        fig.add_trace(go.Scatter(
            x=data['timestamp'],
            y=rsi,
            mode='lines',
            name='RSI',
            line=dict(color='orange'),
            yaxis='y3'
        ))

    # ---- MACD
    if "MACD" in indicators and len(data) >= 26:
        ema12 = data['close'].ewm(span=12, adjust=False).mean()
        ema26 = data['close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        fig.add_trace(go.Scatter(
            x=data['timestamp'],
            y=macd,
            mode='lines',
            name='MACD',
            line=dict(color='green'),
            yaxis='y4'
        ))
        fig.add_trace(go.Scatter(
            x=data['timestamp'],
            y=signal,
            mode='lines',
            name='Signal',
            line=dict(color='red'),
            yaxis='y4'
        ))

    # ---- Layout
    fig.update_layout(
        xaxis=dict(title="Time", rangeslider_visible=False),
        yaxis=dict(title="Price", domain=[0.4, 1]),
        yaxis2=dict(title="Volume", domain=[0.25, 0.4], showgrid=False),
        yaxis3=dict(title="RSI", domain=[0.1, 0.25], showgrid=False),
        yaxis4=dict(title="MACD", domain=[0, 0.1], showgrid=False),
        height=700,
        margin=dict(t=40, b=40),
        legend=dict(orientation='h', y=1.02, x=1, xanchor='right', yanchor='bottom'),
        template="plotly_white"
    )

    return fig

# ---- Run App ----
if __name__ == "__main__":
    app.run(debug=True)

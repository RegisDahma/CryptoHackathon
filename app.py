import os
import base64
import json
import time

import dash
from dash.dependencies import Input, Output, State
import dash_core_components as dcc
import dash_html_components as html
import dash_bootstrap_components as dbc
from datetime import datetime as dt
import flask
import redis
import plotly.graph_objs as go
import pandas as pd
from wordcloud import WordCloud, STOPWORDS

import tasks
from utils.redis import REDIS_URL
from utils.getCurrentPrice import binancePriceFetch
from utils.plotly_wordcloud import plotly_wordcloud as pwc

FEEDS = ["reddit"]

# Redis
redis_instance = redis.StrictRedis.from_url(REDIS_URL, decode_responses=True)
crypto_pairs = redis_instance.hgetall("cryptos_nodupe")

# APIs
binance_client = binancePriceFetch()

# Dash
app = dash.Dash("app", external_stylesheets=[dbc.themes.JOURNAL])
server = app.server


def sidebar_content():
    crypto_meta = [html.Div(" ", id="sidebar-crypto-meta")]

    sentiment_indicator = [
        html.Div(
            [
                html.H3(f"{source.capitalize()}:" if source != "des" else "Overall:"),
                html.Div(" ", id=f"sidebar-sentiment-{source}"),
            ]
        )
        for source in FEEDS + ["des"]
    ]

    contents = crypto_meta + sentiment_indicator
    return html.Div(contents)


def sidebar():
    sidebar_header = dbc.Row([dbc.Col(html.H3("Overall Sentiment"))])
    sidebar_contents = html.Div(
        children=[
            html.Div(
                [
                    dcc.Dropdown(
                        id="sidebar-sentiment-dropdown",
                        options=[
                            {"label": coin, "value": symbol}
                            for coin, symbol in crypto_pairs.items()
                        ],
                        value="BTC",
                        placeholder="Select Cryptocurrency",
                    ),
                ]
            ),
            html.Br(),
            sidebar_content(),
        ]
    )

    sidebar = html.Div(
        id="sidebar", children=[sidebar_header, html.Hr(), sidebar_contents],
    )
    return sidebar


def main_container(id="", header_name="header", short_desc=""):
    dropdowns = html.Div(
        [
            html.H4(header_name, id=header_name),
            html.P(short_desc),
            html.Hr(),
            html.Div(
                [
                    dcc.Dropdown(
                        id=f"main-{id}-dropdown",
                        options=[
                            {"label": coin, "value": symbol}
                            for coin, symbol in crypto_pairs.items()
                        ],
                        multi=True,
                        value="BTC",
                        placeholder="Select Cryptocurrency",
                    ),
                ], style={"width": "50%"}
            ),
        ]
    )

    graph_container = dbc.Row(id=f"main-{id}-container", children=[])

    container = html.Div([dropdowns, graph_container], style={"padding": "25px"})
    return container


def header():
    nav = dbc.Navbar(
        color="dark",
        dark=True,
        className="app-header-container",
        children=[
            # Use row and col to control vertical alignment of logo / brand
            dbc.Row(
                [
                    dbc.Col(
                        html.Img(src="./assets/logo.png", height="45px"),
                        className="col-1 app-header-logo",
                    ),
                    dbc.Col(
                        dbc.NavbarBrand("CryptoHub", className="col-9 app-header-title")
                    ),
                    dbc.Col(
                        children=[
                            dbc.Button(
                                "≡",
                                id="sidebar-toggle-button",
                                outline=True,
                                color="warning",
                                n_clicks=0,
                            ),
                        ],
                        className="mr-1 sidebar-toggle-button",
                    ),
                ],
                align="center",
                no_gutters=True,
            ),
            dbc.NavbarToggler(id="navbar-toggler"),
            dbc.Collapse(
                id="navbar-collapse",
                navbar=True,
                children=[
                    dbc.Row(
                        dbc.Col(dbc.NavLink("Home", href="#")),
                        no_gutters=True,
                        className="ml-auto flex-nowrap mt-3 mt-md-0",
                        align="center",
                    ),
                ],
            ),
        ],
    )
    return nav


def serve_layout():
    return html.Div(
        [
            header(),
            html.Div(
                [
                    dbc.Row(
                        children=[
                            html.Div(
                                id="sidebar-container",
                                className="sidebar-container-show",
                                children=[sidebar()],
                            ),
                            html.Div(
                                id="app-container",
                                children=[
                                    # html.Div(
                                    #     [
                                    #         html.Div(id="status"),
                                    #         dcc.Dropdown(
                                    #             id="dropdown",
                                    #             options=[
                                    #                 {"value": i, "label": i}
                                    #                 for i in ["LA", "NYC", "MTL"]
                                    #             ],
                                    #             value="LA",
                                    #         ),
                                    #         dcc.Graph(id="graph"),
                                    #     ]
                                    # ),
                                    main_container(id="wordmaps", header_name="Wordmaps", short_desc="A visualization of word counts."),
                                ],
                                className="app-contents-container",
                            ),
                        ],
                        className="row-margin-zero",
                    ),
                ],
                className="app-contents",
            ),
            dcc.Interval(interval=5 * 1000, id="interval"),
        ]
    )


app.layout = serve_layout

# CSS Callbacks
# -------------------------------------------------------------------
@app.callback(
    Output("navbar-collapse", "is_open"),
    [Input("navbar-toggler", "n_clicks")],
    [State("navbar-collapse", "is_open")],
)
def toggle_navbar_collapse(n, is_open):
    if n:
        return not is_open
    return is_open


@app.callback(
    [Output("sidebar", "className"), Output("app-container", "className")],
    [Input("sidebar-toggle-button", "n_clicks")],
)
def toggle_sidebar_collapse(n):
    if n % 2 == 0:
        return "sidebar-container-show", "app-contents-container"
    return "sidebar-container-hide", "app-contents-container-full"


@app.callback(
    [
        Output(f"sidebar-sentiment-{provider}", "children")
        for provider in FEEDS + ["des"]
    ]
    + [
        Output(f"sidebar-sentiment-{provider}", "className")
        for provider in FEEDS + ["des"]
    ],
    [Input("sidebar-sentiment-dropdown", "value")],
)
def update_sidebar_sentiment(selected_crypto):
    if selected_crypto == "Bitcoin":

        return ["+2 ▲" for i in range(len(FEEDS) + 1)] + [
            "sidebar-container-sentiment-positive" for i in range(len(FEEDS) + 1)
        ]
    else:
        return ["-1 ▼" for i in range(len(FEEDS) + 1)] + [
            "sidebar-container-sentiment-negative" for i in range(len(FEEDS) + 1)
        ]


# Callbacks
# -------------------------------------------------------------------


@app.callback(
    Output("sidebar-crypto-meta", "children"),
    [Input("sidebar-sentiment-dropdown", "value"), Input("interval", "n_intervals")],
)
def update_sidebar_crypto_meta(selected_crypto, _):
    try:
        price = binance_client.getPrice(selected_crypto)
        curr_time = time.asctime(time.localtime(time.time()))

        formatted_meta = html.Div(
            [
                html.Div(
                    [html.B("Price (Binance):"), html.P(f"{round(float(price), 2)}"),]
                ),
                html.Div([html.B("Time:"), html.P(f"{curr_time}")]),
            ],
        )
    except:
        formatted_meta = html.Div(
            [
                html.B("Error:"),
                html.P(
                    "Selected Coin not listed on Binance. (Try a popular coin like Bitcoin, or Ethereum)"
                ),
            ]
        )

    return formatted_meta


@app.callback(
    Output("main-wordmaps-container", "children"),
    [Input("main-wordmaps-dropdown", "value")],
    [State("main-wordmaps-container", "children")],
)
def render_dynamic_wordmaps(selected_cryptos, container):
    if not isinstance(selected_cryptos, list):
        selected_cryptos = [selected_cryptos]

    container_len = len(container)
    cryptos_len = len(selected_cryptos)

    if cryptos_len == 0:
        return dash.no_update

    if cryptos_len > container_len:
        text = "Wikipedia was launched on January 15, 2001, by Jimmy Wales and Larry Sanger.[10] Sanger coined its name,[11][12] as a portmanteau of wiki[notes 3] and 'encyclopedia'. Initially an English-language encyclopedia, versions in other languages were quickly developed. With 5,748,461 articles,[notes 4] the English Wikipedia is the largest of the more than 290 Wikipedia encyclopedias. Overall, Wikipedia comprises more than 40 million articles in 301 different languages[14] and by February 2014 it had reached 18 billion page views and nearly 500 million unique visitors per month.[15] In 2005, Nature published a peer review comparing 42 science articles from Encyclopadia Britannica and Wikipedia and found that Wikipedia's level of accuracy approached that of Britannica.[16] Time magazine stated that the open-door policy of allowing anyone to edit had made Wikipedia the biggest and possibly the best encyclopedia in the world and it was testament to the vision of Jimmy Wales.[17] Wikipedia has been criticized for exhibiting systemic bias, for presenting a mixture of 'truths, half truths, and some falsehoods',[18] and for being subject to manipulation and spin in controversial topics.[19] In 2017, Facebook announced that it would help readers detect fake news by suitable links to Wikipedia articles. YouTube announced a similar plan in 2018."
        fig = pwc(text)
        col_graph = html.Div(dbc.Col(dcc.Graph(figure=fig)))
        container.append(col_graph)
    elif cryptos_len > 3 or cryptos_len < container_len:
        container.pop()
    return container


def get_dataframe():
    """Retrieve the dataframe from Redis
    This dataframe is periodically updated through the redis task
    """
    jsonified_df = redis_instance.hget(
        tasks.REDIS_HASH_NAME, tasks.REDIS_KEYS["DATASET"]
    )
    df = pd.DataFrame(json.loads(jsonified_df))
    return df


# @app.callback(
#     Output("graph", "figure"),
#     [Input("dropdown", "value"), Input("interval", "n_intervals")],
# )
# def update_graph(value, _):
#     df = get_dataframe()
#     return {
#         "data": [{"x": df["time"], "y": df["value"], "type": "bar"}],
#         "layout": {"title": value},
#     }


# @app.callback(
#     Output("status", "children"),
#     [Input("dropdown", "value"), Input("interval", "n_intervals")],
# )
# def update_status(value, _):
#     data_last_updated = redis_instance.hget(
#         tasks.REDIS_HASH_NAME, tasks.REDIS_KEYS["DATE_UPDATED"]
#     )
#     return "Data last updated at {}".format(data_last_updated)


if __name__ == "__main__":
    app.run_server(debug=True)

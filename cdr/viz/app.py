import argparse
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
import dash
from dash import dcc
from dash import html
from dash.dependencies import Input, Output, State
import base64

from cdr.util import load_cdr, get_irf_name


N_SAMPLES = 10
PLOT_WIDTH = 8
PLOT_HEIGHT = 6
PLOT_DPI = 300
SCREEN_DPI = 72

def get_resparams(model, response):
    resparams = []
    if response in model.response_names:
        for x in model.get_response_params(response):
            for y in model.expand_param_name(response, x):
                resparams.append(y)
    return resparams


def get_surface_colorscale(z):
    blue = np.array((0, 0, 255))
    red = np.array((255, 0, 0))
    gray = np.array((220, 220, 220))

    lower = z.min()
    upper = z.max()
    mag = max(np.abs(upper), np.abs(lower))
    lower_p = lower / mag
    upper_p = upper / mag
    if lower_p < 0:
        lower_c = blue * (-lower_p) + gray * (1 + lower_p)
    else:
        lower_c = red * lower_p + gray * (1 - lower_p)
    if upper_p > 0:
        upper_c = red * upper_p + gray * (1 - upper_p)
    else:
        upper_c = blue * (-upper_p) + gray * (1 + upper_p)

    colorscale = [
        [0., 'rgb(%s, %s, %s)' % tuple(lower_c)],
        [1., 'rgb(%s, %s, %s)' % tuple(upper_c)],
    ]

    if lower_p < 0 and upper_p > 0:
        midpoint = (-lower_p) / (upper_p - lower_p)
        colorscale.insert(1, [midpoint, 'rgb(%s, %s, %s)' % tuple(gray)])

    return colorscale


def initialize_app():
    app = dash.Dash(__name__)
    app.scripts.config.serve_locally = True
    app.config['suppress_callback_exceptions'] = True
    app_name = 'CDR Viewer'
    app_title = 'CDR Viewer'
    app.layout = layout()

    assign_callbacks(app)

    return app


def layout():
    return html.Div(
        id='main_page',
        children=[
            dcc.Location(id='url', refresh=False),
            html.Div(
                id='app-page-content',
                children=html.Div(
                    id='cdrnn-body',
                    className='app-body',
                    children=[
                        viewport_layout(),
                        side_panel_layout()
                    ]
                )
            )
        ],
    )


def viewport_layout():
    graph = dcc.Graph(
        id='graph',
        config=dict(
            editable=True,
            displaylogo=False,
            modeBarButtonsToRemove=['resetCameraDefault3d'],
            toImageButtonOptions=dict(
                format='png',
                filename='cdr_plot',
                width=PLOT_WIDTH * SCREEN_DPI,
                height=PLOT_HEIGHT * SCREEN_DPI,
                scale=PLOT_DPI / SCREEN_DPI
            )
        ),
        style={'width': '70vw', 'height': '100vh'}
    )

    return html.Div(
        id="viewport-wrapper",
        children=dcc.Loading(
            id='viewport-loader',
            type="dot",
            fullscreen=False,
            style={
                'position': 'fixed',
                'top': '50vh',
                'left': '65vw',
            },
            children=graph
        )
    )


def side_panel_layout():
    return html.Div(
        id='side-panel',
        children=[
            html.Button('Update Plot', id='update-button', n_clicks=0),
            dcc.Download(id='download'),
            html.Div(
                id='cdrnn-settings',
                className='control-settings',
                children=[
                    html.Div(
                        id='cdrnn-settings-inner',
                        children=[
                            layout_plot_definition_menu(),
                            layout_reference_values_menu(),
                            layout_uncertainty_menu(),
                            layout_axis_bounds(),
                            layout_aesthetics_menu(),
                            layout_save_menu()
                        ]
                    )
                ]
            )
        ]
    )


def layout_plot_definition_menu():
    xy_axis_options = model.impulse_names + ['t_delta', 'X_time']
    response_options = model.response_names

    return html.Div(
        title='Plot Definition',
        className='app-controls-block',
        children=[
            html.Div(
                className='fullwidth-app-controls-name',
                children=html.Span(
                    'Plot Definition',
                    className='fullwidth-app-controls-name-text'
                )
            ),
            html.Div(
                className='fullwidth-app-controls',
                children=[
                    html.Label(
                        children=[
                            'X axis',
                            dcc.Dropdown(
                                id='dropdown_x',
                                options=[{'label': get_irf_name(i, model.irf_name_map), 'value': i} for
                                         i in xy_axis_options],
                                value=xy_axis_options[xy_axis_options.index('t_delta')],
                                clearable=False
                            )
                        ]
                    ),
                    html.Label(
                        children=[
                            'Y axis (optional)',
                            dcc.Dropdown(
                                id='dropdown_y',
                                options=[{'label': get_irf_name(i, model.irf_name_map), 'value': i} for
                                         i in xy_axis_options],
                                value=xy_axis_options[0],
                                clearable=True
                            )
                        ]
                    ),
                    html.Label(
                        children=[
                            'Response variable',
                            dcc.Dropdown(
                                id='dropdown_response',
                                options=[{'label': get_irf_name(i, model.irf_name_map), 'value': i} for
                                         i in response_options],
                                value=response_options[0],
                                clearable=False
                            )
                        ]
                    ),
                    html.Label(
                        children=[
                            'Response parameter',
                            dcc.Dropdown(
                                id='dropdown_resparams',
                                options=[{'label': x, 'value': x} for x in
                                         get_resparams(model, response_options[0])],
                                value=model.expand_param_name(response_options[0],
                                                              model.get_response_params(
                                                                  response_options[0])[0])[0],
                                clearable=False
                            )
                        ]
                    ),
                    html.Label(
                        children=[
                            dcc.Checklist(
                                id='plot-switches',
                                options=[
                                    {'label': 'Reference varies with X', 'value': 'ref_varies_with_x'},
                                    {'label': 'Reference varies with Y', 'value': 'ref_varies_with_y'},
                                    {'label': 'Pair manipulations', 'value': 'pair_manipulations'},
                                    {'label': 'Include interactions', 'value': 'include_interactions'}
                                ],
                                value=['ref_varies_with_x', 'pair_manipulations']
                            )
                        ]
                    )
                ]
            )
        ]
    )


def layout_reference_values_menu():
    panel_name = html.Div(
        className='fullwidth-app-controls-name',
        children=html.Span(
            'Reference values',
            className='fullwidth-app-controls-name-text'
        )
    )

    reference_settings = []
    for x in model.impulse_names:
        reference_settings.append(
            html.Label(
                id='%s-reference-label' % x,
                children=[
                    get_irf_name(x, model.irf_name_map),
                    dcc.Input(
                        id='%s-reference' % x,
                        type='number',
                        debounce=True,
                        placeholder=model.reference_arr[model.impulse_names_to_ix[x]]
                    )
                ]
            )
        )
    reference_settings.append(
        html.Label(
            id='X-time-reference-label',
            children=[
                'Time',
                dcc.Input(
                    id='X-time-reference',
                    type='number',
                    debounce=True,
                    placeholder=model.X_time_mean
                )
            ]
        )
    )
    reference_settings.append(
        html.Label(
            id='t-delta-reference-label',
            children=[
                get_irf_name('t_delta', model.irf_name_map),
                dcc.Input(
                    id='t-delta-reference',
                    type='number',
                    debounce=True,
                    placeholder=model.reference_time
                )
            ]
        )
    )
    for i, x in enumerate(model.rangf):
        reference_settings.append(
            html.Label(
                id='%s-reference-label' % x,
                children=[
                    x,
                    dcc.Dropdown(
                        id='%s-reference' % x,
                        options=[{'label': y, 'value': y} for y in model.ranef_level2ix[x] if y is not None],
                        value=None,
                        clearable=True
                    )
                ]
            )
        )
    return html.Div(
        title='Reference values',
        className='app-controls-block',
        children=[
            panel_name,
            html.Div(
                className='fullwidth-app-controls',
                children=reference_settings
            )
        ]
    )


def layout_uncertainty_menu():
    return html.Div(
        title='Uncertainty',
        className='app-controls-block',
        children=[
            html.Div(
                className='fullwidth-app-controls-name',
                children=html.Span(
                    'Uncertainty',
                    className='fullwidth-app-controls-name-text'
                )
            ),
            html.Div(
                className='fullwidth-app-controls',
                children=[
                    html.Label(
                        children=[
                            'Number of samples',
                            dcc.Input(
                                id='n_samples',
                                type='number',
                                debounce=True,
                                placeholder=N_SAMPLES,
                                min=0,
                                step=1
                            )
                        ]
                    ),
                    html.Label(
                        children=[
                            'Error interval, 0-100 (default: 95)',
                            dcc.Input(
                                id='ci',
                                type='number',
                                debounce=True,
                                placeholder=95,
                                min=0,
                                max=100,
                                step=1
                            )
                        ]
                    )
                ]
            )
        ]
    )


def layout_axis_bounds():
    return html.Div(
        title='Axis bounds',
        className='app-controls-block',
        children=[
            html.Div(
                className='fullwidth-app-controls-name',
                children=html.Span(
                    'Axis bounds',
                    className='fullwidth-app-controls-name-text'
                )
            ),
            html.Div(
                className='fullwidth-app-controls',
                children=[
                    html.Label(
                        children=[
                            html.Span(
                                'X min',
                                id='x-min-lab'
                            ),
                            dcc.Input(
                                id='x_min',
                                type='number',
                                debounce=True,
                            )
                        ]
                    ),
                    html.Label(
                        children=[
                            html.Span(
                                'X max',
                                id='x-max-lab'
                            ),
                            dcc.Input(
                                id='x_max',
                                type='number',
                                debounce=True,
                            )
                        ]
                    ),
                    html.Label(
                        children=[
                            html.Span(
                                'Y min',
                                id='y-min-lab'
                            ),
                            dcc.Input(
                                id='y_min',
                                type='number',
                                debounce=True,
                            )
                        ]
                    ),
                    html.Label(
                        children=[
                            html.Span(
                                'Y max',
                                id='y-max-lab'
                            ),
                            dcc.Input(
                                id='y_max',
                                type='number',
                                debounce=True,
                            )
                        ]
                    ),
                    html.Label(
                        children=[
                            html.Span(
                                'Z min',
                                id='z-min-lab'
                            ),
                            dcc.Input(
                                id='z_min',
                                type='number',
                                debounce=True,
                            )
                        ]
                    ),
                    html.Label(
                        children=[
                            html.Span(
                                'Z max',
                                id='z-max-lab'
                            ),
                            dcc.Input(
                                id='z_max',
                                type='number',
                                debounce=True,
                            )
                        ]
                    ),
                ]
            )
        ]
    )


def layout_aesthetics_menu():
    return html.Div(
        title='Save Settings',
        className='app-controls-block',
        children=[
            html.Div(
                className='fullwidth-app-controls-name',
                children=html.Span(
                    'Aesthetics',
                    className='fullwidth-app-controls-name-text'
                )
            ),
            html.Div(
                className='fullwidth-app-controls',
                children=[
                    html.Label(
                        children=[
                            html.Label(
                                id='height-label',
                                children=[
                                    'Relative height',
                                    dcc.Input(
                                        id='height',
                                        type='number',
                                        debounce=True,
                                        placeholder=1
                                    )
                                ]
                            ),
                            html.Label(
                                id='plot-title-label',
                                children=[
                                    'Plot title',
                                    dcc.Input(
                                        id='plot-title',
                                        type='text',
                                        debounce=True,
                                        placeholder='Auto'
                                    )
                                ]
                            ),
                            html.Label(
                                id='xlab-label',
                                children=[
                                    'X axis label',
                                    dcc.Input(
                                        id='xlab',
                                        type='text',
                                        debounce=True,
                                        placeholder='Auto'
                                    )
                                ]
                            ),
                            html.Label(
                                id='ylab-label',
                                children=[
                                    'Y axis label',
                                    dcc.Input(
                                        id='ylab',
                                        type='text',
                                        debounce=True,
                                        placeholder='Auto'
                                    )
                                ]
                            ),
                            html.Label(
                                id='zlab-label',
                                children=[
                                    'Z axis label',
                                    dcc.Input(
                                        id='zlab',
                                        type='text',
                                        debounce=True,
                                        placeholder='Auto'
                                    )
                                ]
                            ),
                            dcc.Checklist(
                                id='aes-plot-switches',
                                options=[
                                    {'label': 'Fuzzy', 'value': 'fuzzy'},
                                ],
                                value=[]
                            )
                        ]
                    )
                ]
            )
        ]
    )


def layout_save_menu():
    return html.Div(
        title='Aesthetics',
        className='app-controls-block',
        children=[
            html.Div(
                className='fullwidth-app-controls-name',
                children=html.Span(
                    'Save Settings',
                    className='fullwidth-app-controls-name-text'
                )
            ),
            html.Div(
                className='fullwidth-app-controls',
                children=[
                    html.Label(
                        children=[
                            html.Label(
                                id='save-width-label',
                                children=[
                                    'Width (in.)',
                                    dcc.Input(
                                        id='save-width',
                                        type='number',
                                        debounce=True,
                                        placeholder=PLOT_WIDTH
                                    )
                                ]
                            ),
                            html.Label(
                                id='save-height-label',
                                children=[
                                    'Height (in.)',
                                    dcc.Input(
                                        id='save-height',
                                        type='number',
                                        debounce=True,
                                        placeholder=PLOT_HEIGHT
                                    )
                                ]
                            ),
                            html.Label(
                                id='save-dpi-label',
                                children=[
                                    'DPI (dots per inch)',
                                    dcc.Input(
                                        id='save-dpi',
                                        type='number',
                                        debounce=True,
                                        placeholder=PLOT_DPI
                                    )
                                ]
                            ),
                            html.Label(
                                id='save-name-label',
                                children=[
                                    'Filename',
                                    dcc.Input(
                                        id='save-name',
                                        type='text',
                                        debounce=True,
                                        placeholder='cdr_plot.png'
                                    )
                                ]
                            ),
                        ]
                    )
                ]
            )
        ]
    )


def assign_callbacks(_app):
    update_args = [
        Input('update-button', 'n_clicks'),
        State('graph', 'relayoutData'),
        State('dropdown_x', 'value'),
        State('dropdown_y', 'value'),
        State('dropdown_response', 'value'),
        State('dropdown_resparams', 'value'),
        State('plot-switches', 'value'),
        State('n_samples', 'value'),
        State('ci', 'value'),
        State('x_min', 'value'),
        State('x_max', 'value'),
        State('y_min', 'value'),
        State('y_max', 'value'),
        State('z_min', 'value'),
        State('z_max', 'value'),
        State('X-time-reference', 'value'),
        State('t-delta-reference', 'value'),
        State('height', 'value'),
        State('plot-title', 'value'),
        State('xlab', 'value'),
        State('ylab', 'value'),
        State('zlab', 'value'),
        State('aes-plot-switches', 'value')
    ]
    for x in model.impulse_names + model.rangf:
        update_args.append(State('%s-reference' % x, 'value'))

    @_app.callback(
        Output('graph', 'figure'),
        Output('graph', 'relayoutData'),
        Output('x-min-lab', 'children'),
        Output('x-max-lab', 'children'),
        Output('y-min-lab', 'children'),
        Output('y-max-lab', 'children'),
        Output('z-min-lab', 'children'),
        Output('z-max-lab', 'children'),
        *update_args
    )
    def update_graph(
            *args
    ):
        kwargs = dict(zip([x.component_id for x in update_args], args))
        n_clicks = kwargs['update-button']
        relayout_data = kwargs['graph']
        xvar = kwargs['dropdown_x']
        yvar = kwargs['dropdown_y']
        response = kwargs['dropdown_response']
        resparam = kwargs['dropdown_resparams']
        switches = kwargs['plot-switches']
        n_samples = kwargs['n_samples']
        level = kwargs['ci']
        xmin = kwargs['x_min']
        xmax = kwargs['x_max']
        ymin = kwargs['y_min']
        ymax = kwargs['y_max']
        zmin = kwargs['z_min']
        zmax = kwargs['z_max']
        X_time_ref = kwargs['X-time-reference']
        t_delta_ref = kwargs['t-delta-reference']
        height = kwargs['height']
        plot_title = kwargs['plot-title']
        xlab = kwargs['xlab']
        ylab = kwargs['ylab']
        zlab = kwargs['zlab']
        aes_plot_switches = kwargs['aes-plot-switches']
        X_ref = {}
        gf_y_ref = {}
        for x in model.impulse_names:
            arg = kwargs['%s-reference' % x]
            if arg is not None:
                X_ref[x] = arg
        for x in model.rangf:
            arg = kwargs['%s-reference' % x]
            if arg is not None:
                gf_y_ref[x] = arg

        if 'fuzzy' in aes_plot_switches:
            fuzzy = True
        else:
            fuzzy = False

        if 'ref_varies_with_x' in switches:
            ref_varies_with_x = True
        else:
            ref_varies_with_x = False
        if 'ref_varies_with_y' in switches:
            ref_varies_with_y = True
        else:
            ref_varies_with_y = False
        if 'pair_manipulations' in switches:
            pair_manipulations = True
        else:
            pair_manipulations = False
        if 'include_interactions' in switches:
            include_interactions = True
        else:
            include_interactions = False

        if n_samples is None:
            n_samples = N_SAMPLES
        if ref_varies_with_x is None:
            ref_varies_with_x = xvar in ('t_delta', 'X_time') and yvar is not None
        if ref_varies_with_y is None:
            ref_varies_with_y = yvar in ('t_delta', 'X_time')
        if height is None:
            height = 1

        if xlab is None:
            xlab = get_irf_name(xvar, model.irf_name_map)
        if ylab is None:
            if yvar is None:
                ylab = get_irf_name(response, model.irf_name_map) + ", " + resparam
            else:
                ylab = get_irf_name(yvar, model.irf_name_map)
        if zlab is None:
            zlab = get_irf_name(response, model.irf_name_map) + ", " + resparam

        try:
            plot_data = model.get_plot_data(
                ref_varies_with_x=ref_varies_with_x,
                ref_varies_with_y=ref_varies_with_y,
                xvar=xvar,
                yvar=yvar,
                responses=response,
                response_params=resparam,
                X_ref=X_ref,
                X_time_ref=X_time_ref,
                t_delta_ref=t_delta_ref,
                gf_y_ref=gf_y_ref,
                pair_manipulations=pair_manipulations,
                include_interactions=include_interactions,
                level=level,
                xmin=xmin,
                xmax=xmax,
                ymin=ymin,
                ymax=ymax,
                n_samples=n_samples
            )

            if yvar is None:  # 2D plot
                x2d = plot_data[0]
                d2d = plot_data[1]
                y2d = d2d[response][resparam]
                y2d_splice = y2d[..., 0]
                y_lower = plot_data[2][response][resparam][..., 0]
                y_upper = plot_data[3][response][resparam][..., 0]
                fig = go.Figure(data=[
                    go.Scatter(x=x2d, y=y2d_splice, marker=dict(color='blue'), mode='lines'),
                    go.Scatter(
                        name='Upper Bound',
                        x=x2d,
                        y=y_upper,
                        mode='lines',
                        line=dict(width=0),
                        showlegend=False
                    ),
                    go.Scatter(
                        name='Lower Bound',
                        x=x2d,
                        y=y_lower,
                        line=dict(width=0),
                        mode='lines',
                        fillcolor='rgba(0, 0, 255, 0.2)',
                        fill='tonexty',
                        showlegend=False
                    )
                ])

                if xmin is not None and xmax is not None:
                    fig.update_xaxes(range=[xmin, xmax])
                fig.update_layout(
                    font_family='Helvetica',
                    title_font_family='Helvetica',
                    title=plot_title,
                    xaxis_title=xlab,
                    yaxis_title=ylab,
                    xaxis=dict(range=[xmin, xmax], gridcolor='rgb(200, 200, 200)'),
                    yaxis=dict(gridcolor='rgb(200, 200, 200)'),
                    plot_bgcolor='rgb(255, 255, 255)',
                    paper_bgcolor='rgb(255, 255, 255)'
                )
            else:  # 3D plot
                zmin = zmin
                zmax = zmax
                x, y = plot_data[0]
                z = plot_data[1][response][resparam]
                z_lower = plot_data[2][response][resparam]
                z_upper = plot_data[3][response][resparam]

                fig = go.Figure()
                traces = []
                for i in range(z.shape[-1]):
                    _z = z[..., i]
                    traces.append(
                        go.Surface(
                            z=_z,
                            x=x,
                            y=y,
                            colorscale=get_surface_colorscale(_z),
                            showscale=False,
                            lighting=dict(
                                ambient=1.0,
                                diffuse=1.0
                            )
                        )
                    )
                    if n_samples:
                        if fuzzy:
                            _z_lower = z_lower[..., i]
                            _z_upper = z_upper[..., i]
                            for _x, _y, _zmin, _zmax in zip(x.flatten(), y.flatten(), _z_lower.flatten(),
                                                            _z_upper.flatten()):
                                traces.append(
                                    go.Scatter3d(
                                        x=(_x, _x),
                                        y=(_y, _y),
                                        z=(_zmin, _zmax),
                                        mode='lines',
                                        line=dict(
                                            color='rgba(0, 0, 0, 0.15)',
                                            width=3
                                        )
                                    )
                                )
                            fig.add_traces(traces)
                        else:
                            _z_lower = z_lower[..., i]
                            _z_upper = z_upper[..., i]
                            traces.append(
                                go.Surface(
                                    z=_z_lower,
                                    x=x,
                                    y=y,
                                    colorscale=get_surface_colorscale(_z_lower),
                                    opacity=0.4,
                                    showscale=False,
                                    lighting=dict(
                                        ambient=1.0,
                                        diffuse=1.0
                                    )
                                )
                            )
                            traces.append(
                                go.Surface(
                                    z=_z_upper,
                                    x=x,
                                    y=y,
                                    colorscale=get_surface_colorscale(_z_upper),
                                    opacity=0.4,
                                    showscale=False,
                                    lighting=dict(
                                        ambient=1.0,
                                        diffuse=1.0
                                    )
                                )
                            )

                fig.add_traces(traces)

                layout_kwargs = dict(
                    font_family='Helvetica',
                    title_font_family='Helvetica',
                    title=plot_title,
                    scene=dict(
                        xaxis_title=xlab,
                        yaxis_title=ylab,
                        zaxis_title=zlab,
                        xaxis=dict(range=[xmin, xmax], gridcolor='rgb(200, 200, 200)', showbackground=False,
                                   autorange='reversed'),
                        yaxis=dict(range=[ymin, ymax], gridcolor='rgb(200, 200, 200)', showbackground=False,
                                   autorange='reversed'),
                        zaxis=dict(range=[zmin, zmax], gridcolor='rgb(200, 200, 200)', showbackground=False)
                    ),
                    plot_bgcolor='rgb(255, 255, 255)',
                    paper_bgcolor='rgb(255, 255, 255)',
                    scene_aspectmode='manual',
                    scene_aspectratio=dict(x=1, y=1, z=height),
                    margin=dict(r=20, l=20, b=20, t=20),
                    showlegend=False
                )
                if False and n_clicks == 0:
                    layout_kwargs['scene_camera'] = dict(
                        up=dict(x=0, y=0, z=1),
                        center=dict(x=0, y=0, z=0),
                        eye=dict(x=1.25, y=-1.25, z=1)
                    )

                fig.update_layout(**layout_kwargs)
                fig = fig.to_dict()
                fig['layout']['uirevision'] = True

        except AssertionError as e:
            msg = ''
            msg_src = ('Invalid plot settings. %s' % e).split()
            line = ''
            while msg_src:
                w = msg_src.pop(0)
                if not line:
                    line += w
                else:
                    line += ' ' + w
                if len(line) > 50:
                    if msg:
                        msg += '<br>' + line
                    else:
                        msg += line
                    line = ''
            if msg:
                msg += '<br>' + line
            else:
                msg += line
            fig = {
                'layout': {
                    'xaxis': {
                        'visible': False
                    },
                    'yaxis': {
                        'visible': False
                    },
                    'annotations': [
                        {
                            'text': msg,
                            'xref': 'paper',
                            'yref': 'paper',
                            'showarrow': False,
                            'font': {
                                'size': 16
                            }
                        }
                    ]
                }
            }

        x_min_lab = '%s min' % (get_irf_name(xvar, model.irf_name_map))
        x_max_lab = '%s max' % (get_irf_name(xvar, model.irf_name_map))
        if yvar:
            y_min_lab = '%s min' % (get_irf_name(yvar, model.irf_name_map))
            y_max_lab = '%s max' % (get_irf_name(yvar, model.irf_name_map))
        else:
            y_min_lab = 'Y min'
            y_max_lab = 'Y max'
        z_min_lab = '%s, %s min' % (get_irf_name(response, model.irf_name_map), resparam)
        z_max_lab = '%s, %s max' % (get_irf_name(response, model.irf_name_map), resparam)

        return fig, relayout_data, x_min_lab, x_max_lab, y_min_lab, y_max_lab, z_min_lab, z_max_lab

    @_app.callback(
        Output('graph', 'config'),
        Input('save-width', 'value'),
        Input('save-height', 'value'),
        Input('save-dpi', 'value'),
        Input('save-name', 'value'),
        State('graph', 'config')
    )
    def update_graph_config(
            save_width,
            save_height,
            save_dpi,
            filename,
            graph_config
    ):
        if save_width is None:
            save_width = PLOT_WIDTH
        if save_height is None:
            save_height = PLOT_HEIGHT
        if save_dpi is None:
            save_dpi = PLOT_DPI
        if filename is None:
            filename = 'cdr_plot'
        if filename.endswith('.png'):
            filename = filename[:-4]

        plot_width = save_width * SCREEN_DPI
        plot_height = save_height * SCREEN_DPI
        plot_scale = save_dpi / SCREEN_DPI

        graph_config['toImageButtonOptions']['width'] = plot_width
        graph_config['toImageButtonOptions']['height'] = plot_height
        graph_config['toImageButtonOptions']['scale'] = plot_scale
        graph_config['toImageButtonOptions']['filename'] = filename

        return graph_config

if __name__ == '__main__':
    argparser = argparse.ArgumentParser("""
    Start a web server for interactive CDR visualization.
    """)
    argparser.add_argument('model', help='Path to model directory')
    argparser.add_argument('-d', '--debug', action='store_true', help='Whether to run in debug mode.')
    args = argparser.parse_args()

    model = load_cdr(args.model)
    model.set_predict_mode(True)

    app = initialize_app()

    server = app.server
    app.run_server(debug=args.debug, port=5000)

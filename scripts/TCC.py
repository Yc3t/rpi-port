import numpy as np
import scipy as sp
from scipy import integrate
import math
from numpy import array
from scipy.optimize import fsolve
from scipy import special
import sys, os
import plotly.graph_objs as go
import plotly.io as pio
import json


def fdispT(Dist):
    LIM =(pcw*u)**2*Tiempo/(4*pc*lx)
    integrando = lambda n: (1/(n))*np.exp(-n-(Dist**2/lx+ 0.0**2/ly)*(u*pcw)**2/(16*n*lx))
    integral, err = sp.integrate.quad(integrando, 0, LIM)
    A = IncT *(4*math.pi*math.sqrt(lx*ly))/(np.exp(u*Dist*pcw/(2*lx)))
    C = A / integral
    return  C

def fdispTW(DistPer):
    LIM =(pcw*u)**2*Tiempo/(4*pc*lx)
    integrando = lambda n: (1/(n))*np.exp(-n-(0.0**2/lx+ DistPer**2/ly)*(u*pcw)**2/(16*n*lx))
    integral, err = sp.integrate.quad(integrando, 0, LIM)
    A = IncT *(4*math.pi*math.sqrt(lx*ly))/( np.exp(u*(0.0*2)*pcw/(2*lx)))
    C = A / integral
    return  C

def fdispE(Dist):
    A = IncT *(2*math.pi*math.sqrt(lx*ly))/ np.exp(u*Dist*pcw/(2*lx)) / special.kv(0, 0.5*pcw *u*math.sqrt((ly*Dist**2 + lx*0.0**2)/(ly*lx**2)) )
    return  A

def fdispEW(DistPer):
    A = IncT *(2*math.pi*math.sqrt(lx*ly))/ np.exp(u*(0.0)*pcw/(2*lx)) / special.kv(0, 0.5*pcw *u*math.sqrt((ly*(0.0)**2 + lx*DistPer**2)/(ly*lx**2)) )
    return  A

def fdispEmaxHR(Dist, T):
    A = T *(2*math.pi*math.sqrt(lx*ly))/ np.exp(u*Dist*pcw/(2*lx)) / special.kv(0, 0.5*pcw *u*math.sqrt((ly*Dist**2 + lx*0.0**2)/(ly*lx**2)) )
    return  A

def fdispTmaxHR(Dist,T):
    LIM =(pcw*u)**2*Tiempo/(4*pc*lx)
    integrando = lambda n: (1/(n))*np.exp(-n-(Dist**2/lx+ 0.0**2/ly)*(u*pcw)**2/(16*n*lx))
    integral, err = sp.integrate.quad(integrando, 0, LIM)
    A = T *(4*math.pi*math.sqrt(lx*ly))/( np.exp(u*Dist*pcw/(2*lx)))
    C = A / integral
    return  C

def HR_norm_fdispT(Dist):
    LIM =(pcw*u)**2*Tiempo/(4*pc*lx)
    integrando = lambda n: (1/(n))*np.exp(-n-(Dist**2/lx+ 0.0**2/ly)*(u*pcw)**2/(16*n*lx))
    integral, err = sp.integrate.quad(integrando, 0, LIM)
    A = IncT *(4*math.pi*math.sqrt(lx*ly))/( np.exp(u*Dist*pcw/(2*lx)))
    C = A / integral
    return  math.log(abs(C/Dist))

def aquitards (Dist):
    return - IncT * (4*math.pi*k) / (special.expi(Dist**2/(4*a*Tiempo)))

# Define la función del denominador de aquitards
def f(x):
    return special.expi(x**2 / (4 * a * Tiempo))

# Función para generar el gráfico de Plotly
def generate_plotly_graph(layer_name, d, x, y):
    traces = []
    
    if layer_name in ["U1", "U3"]:
        traces.extend([
            # Width for transient thermal state 
            go.Scatter(x=d, y=list(map(fdispTW, d)), mode='lines', line=dict(color='blue'), name='Width for transient thermal state'),
            # Length for transient thermal state
            go.Scatter(x=d, y=list(map(fdispT, d)), mode='lines', line=dict(color='red'), name='Length for transient thermal state'),
            # Maximum SGE potential allowed
            go.Scatter(x=d, y=[maxHR] * len(d), mode='lines', line=dict(dash='dash', color='black'), name=f'Maximum SGE potential allowed: {round(maxHR,1)} W/m')
        ])
    else:  # Para aquitards (U2 y U4)
        y_values = list(map(aquitards, d))
        traces.append(go.Scatter(x=d, y=y_values, mode='lines', line=dict(color='blue'), name='Diameter for transient thermal state in aquitards'))
        
        # Añadir una línea horizontal en y=0 para mejorar la visualización
        traces.append(go.Scatter(x=[min(d), max(d)], y=[0, 0], mode='lines', line=dict(color='black', dash='dash'), name='Zero line'))

    layout = go.Layout(
        title= title_graph,
        xaxis=dict(title='Distance from BHE in m'),
        yaxis=dict(title='SGP in W/m'),
        legend=dict(x=0, y=1, traceorder='normal'),
        hovermode='closest',
        annotations=[
            dict(
                x=0.5,  # 5% desde la izquierda del gráfico
                y=0.95,  # 95% desde abajo del gráfico
                xref='paper',
                yref='paper',
                showarrow=False,
                font=dict(size=12, color='black'),
                bgcolor='rgba(255,255,255,0.8)',
                bordercolor='black',
                borderwidth=1,
                borderpad=4,
                align='left'
            )
        ]
    )

    # Generar el gráfico de Plotly
    fig = go.Figure(data=traces, layout=layout)
    
    return pio.to_json(fig)

# Main execution
if __name__ == "__main__":
    try:
        # Print argument count for debugging
        print(f"Received {len(sys.argv) - 1} arguments", file=sys.stderr)
        for i, arg in enumerate(sys.argv):
            print(f"Argument {i}: {arg}", file=sys.stderr)
            
        # Definimos las entradas
        x = float(sys.argv[1])
        y = float(sys.argv[2])
        layer_name = sys.argv[3]
        title_graph = 'TCC: ' + layer_name + ' - ' + sys.argv[11]

        # Variables comunes
        k = float(sys.argv[5])
        pc = float(sys.argv[7])
        pcw = 4180000
        IncT = float(sys.argv[6])
        Tiempo = float(sys.argv[8])*30*24*3600

        if layer_name in ["U1", "U3"]:
            u = float(sys.argv[4])
            dx = float(sys.argv[9])
            dy = float(sys.argv[10])

            lx = k + dx * pcw * u
            ly = k + dy * pcw * u

            MinDist = 15
            MaxDist = 50
            maxHR = fdispEmaxHR(0.25,5)
            maxHRT = fdispTmaxHR(0.25,5)
            Paso = 0.031
            d = np.arange(-MinDist, MaxDist, Paso)

        else:  # Para aquitards
            a = k / pc
            # Encuentra el valor de x para el cual f(x) = 0
            LimiteEjeX = fsolve(f, 10)  # El 10 es una semilla para la búsqueda de la raíz
            Paso = LimiteEjeX/100
            d = np.arange(-LimiteEjeX*0.999, LimiteEjeX, Paso)

        # Generar los datos del gráfico
        plotly_json = generate_plotly_graph(layer_name, d, x, y)

        result = {
            "plotly_data": json.loads(plotly_json),
            "parameters": {
                "title": title_graph,
                "x": x,
                "y": y,
                "layer_name": layer_name,
                "u": u if layer_name in ["U1", "U3"] else None,
                "k": k,
                "IncT": IncT,
                "pc": pc,
                "Tiempo": Tiempo / (30 * 24 * 3600),  # Convertir de vuelta a meses
                "dx": dx if layer_name in ["U1", "U3"] else None,
                "dy": dy if layer_name in ["U1", "U3"] else None,
            }
        }

        # Imprimir los datos como JSON
        print(json.dumps(result)) 

    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        print(f"Exception executing TCC.py: {str(e)}\n{traceback_str}")
        result = {
            "error": str(e),
            "traceback": traceback_str,
            "message": "Error al ejecutar TCC.py"
        }
        print(json.dumps(result)) 


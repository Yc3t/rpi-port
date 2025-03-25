import math
import numpy as np
import sys
import json
import traceback
from scipy import special
from scipy.optimize import fsolve
from scipy.integrate import quad
from scipy.interpolate import splprep, splev
from pyproj import Transformer

def numpy_to_python(obj):
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, list):
        return [numpy_to_python(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: numpy_to_python(value) for key, value in obj.items()}
    else:
        return obj

try:
    # Print debug info for arguments
    print(f"Received {len(sys.argv) - 1} arguments", file=sys.stderr)
    for i, arg in enumerate(sys.argv):
        print(f"Arg {i}: {arg}", file=sys.stderr)
    
    # Definimos las entradas
    lon = float(sys.argv[1])
    lat = float(sys.argv[2])
    layer_name = sys.argv[3]
    Ql = float(sys.argv[5])
    k = float(sys.argv[6])
    IncT = float(sys.argv[7])
    pc = float(sys.argv[8])
    Tiempo = float(sys.argv[9]) * 30 * 24 * 3600
    pcw = 4180000
    flow_feature = None if sys.argv[12] == 'null' else json.loads(sys.argv[12])

    # Inicializar variables
    flow_coordinates = None
    major_axis = None
    minor_axis = None
    angle = 0

    if layer_name in ["U1", "U3"]:
        u = float(sys.argv[4]) if sys.argv[4] else 0
        dx = None if sys.argv[10] == 'None' else float(sys.argv[10])
        dy = None if sys.argv[11] == 'None' else float(sys.argv[11])
        lx = k + dx*pcw*u
        ly = k + dy*pcw*u

        # Ahora tenemos acceso directo a la geometría y propiedades de la línea
        if flow_feature and 'geometry' in flow_feature:
            flow_line = flow_feature["geometry"]
            flow_coordinates = flow_line.get("coordinates", None)

        def z_func(x):
            integrand = lambda n,x: (1/(n))*np.exp(-n-(x**2/lx+0**2/ly)*(u*pcw)**2/(16*n*lx))
            TimeDisc = (-1+np.sqrt(1+4* (((x**2/lx + 0**2/ly)*(pcw*u)**2)/(16*lx))))/(2)
            integral, err = quad(integrand, 0, (pcw*u)**2*Tiempo/(4*pc*lx), args=(x))
            return IncT*4*np.pi* np.sqrt(lx*ly)/(Ql*np.exp(pcw * u *x/(2*lx)))-integral

        def z_funcY(y):
            integrand = lambda n: (1/(n))*np.exp(-n-(x**2/lx+y**2/ly)*(u*pcw)**2/(16*n*lx))
            TimeDisc = (-1+np.sqrt(1+4* (((x**2/lx + y**2/ly)*(pcw*u)**2)/(16*lx))))/(2)
            integral, err = quad(integrand, 0, (pcw*u)**2*Tiempo/(4*pc*lx))
            return (IncT*4*np.pi* np.sqrt(lx*ly))/(Ql*np.exp(pcw * u *x/(2*lx)))-integral

        # Calcular límites
        Lim1 = fsolve(z_func, 0.01, xtol=1e-10)[0]
        Lim2 = fsolve(z_func, -0.01)[0]
        
        if int(Lim1) == int(Lim2):
            Lim2 = fsolve(z_func, -Lim1/100)[0]

        SupLim = max(Lim1, Lim2)
        InfLim = min(Lim1, Lim2)

        # Calcular puntos
        m = np.linspace(InfLim, SupLim, 50)
        n = []
        for w in m:
            x = w
            if w < 0:    
                integral = abs(fsolve(z_funcY, -0.01)[0])
                n.append(integral)
            elif w > 0:
                integral = abs(fsolve(z_funcY, 0.01)[0])
                n.append(integral)
            else:
                n.append(abs(InfLim))

        major_axis = max(max(n), abs(SupLim))
        minor_axis = min(max(n), abs(SupLim))
        angle = math.atan2(dy, dx)
    else:
        a = k/pc
        def f1(x):
            return -Ql*special.expi(x**2/(4*a*Tiempo))/(4*math.pi*k)-IncT
        major_axis = minor_axis = fsolve(f1, 0.01)[0]
        angle = 0
        flow_coordinates = None

    def create_plume(center_lon, center_lat, major_axis, minor_axis, angle, flow_coordinates, num_points=1400):
        to_utm = Transformer.from_crs('EPSG:4326', 'EPSG:22185', always_xy=True)
        to_wgs84 = Transformer.from_crs('EPSG:22185', 'EPSG:4326', always_xy=True)
        
        if flow_coordinates is None:
            # Convertir el centro a coordenadas UTM
            center_x, center_y = to_utm.transform(center_lon, center_lat)

            # Crear la pluma en coordenadas UTM
            theta = np.linspace(0, 2 * np.pi, num_points)
            x = (major_axis / 2) * np.cos(theta)
            y = (minor_axis / 2) * np.sin(theta)
            
            # Rotar la elipse si es necesario
            rotated_x = x * np.cos(angle) - y * np.sin(angle)
            rotated_y = x * np.sin(angle) + y * np.cos(angle)
            
            # Añadir el centro
            utm_points = [(center_x + xi, center_y + yi) for xi, yi in zip(rotated_x, rotated_y)]
            
            # Convertir de vuelta a coordenadas geográficas
            polygon_points = [to_wgs84.transform(x, y) for x, y in utm_points]
            
            # Cerrar el polígono
            polygon_points.append(polygon_points[0])
            
            return polygon_points
        
        else:
            to_utm = Transformer.from_crs('EPSG:4326', 'EPSG:22185', always_xy=True)
            to_wgs84 = Transformer.from_crs('EPSG:22185', 'EPSG:4326', always_xy=True)
            
            # Convertir el punto de clic y coordenadas de flujo a UTM
            click_x_utm, click_y_utm = to_utm.transform(center_lon, center_lat)
            click_point = np.array([click_x_utm, click_y_utm])
            
            # Convertir coordenadas de flujo a UTM
            flow_coords_utm = []
            for coord in flow_coordinates:
                x_utm, y_utm = to_utm.transform(coord[0], coord[1])
                flow_coords_utm.append([x_utm, y_utm])
            flow_coords_utm = np.array(flow_coords_utm)

            # Encontrar el segmento más cercano
            distances = np.linalg.norm(flow_coords_utm - click_point, axis=1)
            closest_idx = np.argmin(distances)
                
            # Obtener el segmento que atraviesa la pluma
            if closest_idx < len(flow_coords_utm) - 1:
                p1 = flow_coords_utm[closest_idx]
                p2 = flow_coords_utm[closest_idx + 1]
            else:
                p1 = flow_coords_utm[closest_idx - 1]
                p2 = flow_coords_utm[closest_idx]
                
            # Calcular la dirección del segmento
            flow_direction = p2 - p1
            flow_direction = flow_direction / np.linalg.norm(flow_direction)
                
            # Calcular el ángulo de la dirección del flujo
            angle = math.atan2(flow_direction[1], flow_direction[0])  # Cambiar el ángulo según la dirección del flujo
                
            # Vector perpendicular
            perpendicular = np.array([-flow_direction[1], flow_direction[0]])
                
            # Generar puntos de la elipse base sin desplazamiento
            theta = np.linspace(0, 2 * np.pi, num_points, endpoint=False)
            points = []
            for t in theta:
                point = flow_direction * (major_axis * np.cos(t)) + perpendicular * (minor_axis * np.sin(t))
                points.append(point)
                
            # Convertir a array numpy
            points_utm = np.array(points)
                
            # Encontrar el punto más "atrás" en la dirección del flujo
            # Proyectamos los puntos sobre la dirección del flujo
            projections = np.dot(points_utm, flow_direction)
            start_idx = np.argmin(projections)
            start_point = points_utm[start_idx]
                
            # Calcular el desplazamiento necesario para que el inicio coincida con p1
            displacement = p1 #- start_point #Esto es para desplazar la pluma al origen de la linea de flujo
                
            # Aplicar el desplazamiento a todos los puntos
            points_utm = points_utm + displacement
                
            # Suavizado
            tck, u = splprep([points_utm[:, 0], points_utm[:, 1]], s=0, per=1, k=5)
            u_new = np.linspace(0, 1, num_points * 8)
            smooth_points_utm = np.array(splev(u_new, tck)).T
                
            # Convertir a WGS84
            polygon_points = []
            prev_point = None
            for point in smooth_points_utm:
                lon_point, lat_point = to_wgs84.transform(point[0], point[1])
                if prev_point is None or abs(prev_point[0] - lon_point) > 1e-7 or abs(prev_point[1] - lat_point) > 1e-7:
                    polygon_points.append([lon_point, lat_point])
                    prev_point = [lon_point, lat_point]
                
            # Cerrar el polígono
            polygon_points.append(polygon_points[0])
            return polygon_points

    # Crear el polígono
    polygon_points = create_plume(lon, lat, major_axis, minor_axis, angle, flow_coordinates)

    # Crear respuesta GeoJSON
    geojson_feature = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "major_axis": float(major_axis),
                "minor_axis": float(minor_axis),
                "angle": float(angle),
                "center": [float(lon), float(lat)],
                "feature_type": "plume"  # Identificador para la pluma
            },
            "information": {
                "darcy_vel": float(u) if flow_feature is not None else None,
                "layer_name": str(layer_name),
                "heat_rate": float(Ql),
                "thresh_temp": float(IncT),
                "cond_ther": float(k),
                "heat_cap": float(pc),
                "oper_time": float(Tiempo)
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [polygon_points]
            }
        },
        {
            "type": "Feature",
            "properties": {
                "feature_type": "point",  # Identificador para el punto
                "description": "Probe location",
                "lon": float(lon), 
                "lat": float(lat)
            },
            "geometry": {
                "type": "Point",
                "coordinates": [float(lon), float(lat)]
            }
        }
    ]}

    print(json.dumps(geojson_feature))

except Exception as e:
    print(json.dumps({
        "status": "error",
        "error": str(e),
        "message": "Error en el cálculo de la pluma"
    }))
    sys.exit(1)


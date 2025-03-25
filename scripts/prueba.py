import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import RegularGridInterpolator
import sys
from pyproj import Transformer
import json
from rasterio.io import MemoryFile
import psycopg2


def obtener_raster_piezometria(conn, layer_id):
    try:
        cur = conn.cursor()
        # Obtener el raster de piezometría
        cur.execute("""
            SELECT ST_AsTIFF(ST_Union(rast)) as tiff,
                   ST_Envelope(ST_Union(rast)) as envelope
            FROM public.rasters 
            WHERE capa_id = %s AND filename = 'Piezometry'
        """, (layer_id,))
        
        resultado = cur.fetchone()
        if not resultado:
            return None
            
        # Leer el raster desde los datos TIFF
        with MemoryFile(resultado[0]) as memfile:
            with memfile.open() as dataset:
                # Leer los datos del raster
                array = dataset.read(1)
                transform = dataset.transform
                nodata = dataset.nodata
                crs = dataset.crs
                
        return {
            'array': array,
            'transform': transform,
            'nodata': nodata,
            'crs': crs
        }
        
    except Exception as e:
        print(f"Error al obtener el raster: {e}")
        return None

def transformar_coordenadas(lon, lat):
    """
    Transforma coordenadas de EPSG:4326 (lon/lat) a EPSG:22185 (metros)
    """
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:22185", always_xy=True)
    x, y = transformer.transform(lon, lat)
    return x, y

def transformar_coordenadas_inversa(x, y):
    """
    Transforma coordenadas de EPSG:22185 (metros) a EPSG:4326 (lon/lat)
    """
    transformer = Transformer.from_crs("EPSG:22185", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return lon, lat

def calcular_steepest_path(raster_data, punto_inicio_x, punto_inicio_y, max_distancia=None, min_pendiente=0.00001):
    def debug_print(msg):
        print(msg, file=sys.stderr)
    
    debug_print(f"Iniciando cálculo desde punto ({punto_inicio_x}, {punto_inicio_y})")
    
    # Usar el raster de la base de datos
    elevacion = raster_data['array']
    transform = raster_data['transform']
    
    # Convertir coordenadas del mundo real a índices del raster
    px = int((punto_inicio_x - transform[2]) / transform[0])
    py = int((punto_inicio_y - transform[5]) / transform[4])
    debug_print(f"Punto inicial en índices del raster: ({px}, {py})")
    
    # Verificar que el punto está dentro del raster
    if (px < 0 or px >= elevacion.shape[1] or py < 0 or py >= elevacion.shape[0]):
        raise ValueError("El punto inicial está fuera del raster")
    
    # El resto del código permanece igual, pero usando transform en lugar de geotransform
    y = np.arange(elevacion.shape[0])
    x = np.arange(elevacion.shape[1])
    
    interpolador = RegularGridInterpolator((y, x), elevacion, 
                                         method='linear',
                                         bounds_error=False, 
                                         fill_value=None)
    
    # Lista para almacenar el camino
    path = [(px, py)]
    distancia_total = 0
    
    # Parámetros de búsqueda ajustados
    paso = 0.5         # Ajustado para mejor balance entre precisión y estabilidad
    num_direcciones = 36 # Aumentado para mejor resolución angular
    
    iteracion = 0
    max_iteraciones = 100000  # Límite de seguridad
    
    while iteracion < max_iteraciones:
        x, y = path[-1]
        debug_print(f"Iteración {iteracion}: Punto actual ({x}, {y})")
        
        # Verificación más estricta de límites
        margen = 5  # margen de seguridad
        if (x < margen or x > elevacion.shape[1] - margen or 
            y < margen or y > elevacion.shape[0] - margen):
            debug_print("Llegó al límite del raster")
            break
            
        # Calcular pendientes con verificación adicional
        pendientes = []
        angulos = np.linspace(0, 2*np.pi, num_direcciones)
        
        for angulo in angulos:
            i = paso * np.cos(angulo)
            j = paso * np.sin(angulo)
            
            nuevo_y, nuevo_x = y + j, x + i
            
            # Verificar que el nuevo punto está dentro de los límites antes de calcularlo
            if (nuevo_x < margen or nuevo_x > elevacion.shape[1] - margen or 
                nuevo_y < margen or nuevo_y > elevacion.shape[0] - margen):
                continue
            
            # Calcular el ángulo entre el último segmento y el nuevo segmento
            if len(path) > 1:
                dx_prev = x - path[-2][0]
                dy_prev = y - path[-2][1]
                dx_new = nuevo_x - x
                dy_new = nuevo_y - y
                
                angulo_prev = np.arctan2(dy_prev, dx_prev)
                angulo_nuevo = np.arctan2(dy_new, dx_new)
                diferencia_angulo = abs(angulo_nuevo - angulo_prev)
                
                # Convertir la diferencia a radianes y asegurarse de que no exceda 90 grados
                if diferencia_angulo > np.pi / 4:  # Permitir giros más amplios
                    continue
            
            try:
                elev_nuevo = interpolador(np.array([nuevo_y, nuevo_x]))
                elev_actual = interpolador(np.array([y, x]))
                
                # Cálculo más preciso de la distancia real
                distancia_real = np.sqrt((i*transform[0])**2 + (j*transform[4])**2)
                pendiente = (elev_actual - elev_nuevo) / distancia_real
                
                # Factor de corrección para favorecer la dirección principal
                if len(path) > 1:
                    dx_prev = x - path[-2][0]
                    dy_prev = y - path[-2][1]
                    angulo_prev = np.arctan2(dy_prev, dx_prev)
                    diff_angulo = abs(angulo - angulo_prev) % (2*np.pi)
                    if diff_angulo > np.pi:
                        diff_angulo = 2*np.pi - diff_angulo
                    if diff_angulo > np.pi/2:  # Ignorar direcciones muy diferentes
                        continue
                    factor_direccion = np.cos(diff_angulo/2) ** 0.5  # Exponente reducido para suavizado más sutil
                    pendiente *= factor_direccion
                
                pendientes.append((pendiente, (nuevo_x, nuevo_y)))
            except ValueError:
                continue
        
        if not pendientes:
            debug_print("No se encontraron pendientes válidas")
            break
            
        # Encontrar la máxima pendiente
        max_pendiente = max(pendientes, key=lambda x: x[0])
        debug_print(f"Pendiente máxima encontrada: {max_pendiente[0]}")
        
        # Verificar pendiente mínima
        if max_pendiente[0] <= min_pendiente:
            debug_print(f"Se encontró un mínimo local (pendiente {max_pendiente[0]} <= {min_pendiente})")
            break
            
        # Agregar el siguiente punto
        next_point = max_pendiente[1]
        path.append(next_point)
        
        # Actualizar distancia
        dx = (next_point[0] - x) * transform[0]
        dy = (next_point[1] - y) * transform[4]
        distancia_total += np.sqrt(dx**2 + dy**2)
        
        iteracion += 1
    
    if iteracion >= max_iteraciones:
        debug_print("Se alcanzó el máximo número de iteraciones")
    
    debug_print(f"Longitud del path: {len(path)} puntos")
    
    # Al convertir coordenadas, usar transform en lugar de geotransform
    path_world = []
    for px, py in path:
        x = transform[2] + px * transform[0]
        y = transform[5] + py * transform[4]
        path_world.append([x, y])
    
    return path, path_world

def visualize_path(raster_path, path, titulo):
    try:
        import gdal
        ds = gdal.Open(raster_path)
        elevacion = ds.GetRasterBand(1).ReadAsArray()
        
        # Crear visualización
        fig, ax = plt.subplots(figsize=(12,10))
        
        # Mostrar el raster con sombreado
        im = ax.imshow(elevacion, cmap='terrain')
        
        # Mostrar el camino
        path_x = [p[0] for p in path]
        path_y = [p[1] for p in path]
        line = ax.plot(path_x, path_y, 'r-', linewidth=2, label='Línea de máxima pendiente')
        
        # Añadir elementos visuales
        plt.colorbar(im, label='Elevación (m)')
        ax.set_title(titulo)
        ax.set_xlabel('Este (m)')
        ax.set_ylabel('Norte (m)')
        ax.legend()
        
        return fig, ax
    except ImportError:
        print("GDAL not available, skipping visualization", file=sys.stderr)
        return None, None
    except Exception as e:
        print(f"Error in visualization: {e}", file=sys.stderr)
        return None, None

try:
    print("Debug: Starting script...", file=sys.stderr)
    x = float(sys.argv[1])
    y = float(sys.argv[2])
    layer_id = int(sys.argv[3])
    print(f"Debug: Parsed coordinates: x={x}, y={y}, layer_id={layer_id}", file=sys.stderr)

    # Establecer conexión con la base de datos
    print("Debug: Connecting to database...", file=sys.stderr)
    conn = psycopg2.connect(
        host="localhost",
        database="b2",
        user="postgres",
        password="postgres"
    )
    print("Debug: Database connection successful", file=sys.stderr)

    # Obtener el raster de la base de datos
    print("Debug: Fetching raster data...", file=sys.stderr)
    raster_data = obtener_raster_piezometria(conn, layer_id)
    if not raster_data:
        raise Exception("No se pudo obtener el raster de piezometría")
    print("Debug: Raster data obtained successfully", file=sys.stderr)

    # Transformar coordenadas de lat/lon a metros
    print("Debug: Transforming coordinates...", file=sys.stderr)
    punto_inicio_x, punto_inicio_y = transformar_coordenadas(x, y)
    print(f"Debug: Transformed coordinates: x={punto_inicio_x}, y={punto_inicio_y}", file=sys.stderr)

    # Calcular el camino usando el raster de la base de datos
    print("Debug: Calculating steepest path...", file=sys.stderr)
    path, path_world = calcular_steepest_path(
        raster_data,  # Pasamos el raster_data en lugar del path
        punto_inicio_x, 
        punto_inicio_y,
        max_distancia=None,
        min_pendiente=0.0001,
    )
    print(f"Debug: Path calculation complete. Path length: {len(path)}", file=sys.stderr)

    if len(path) > 1:
        print("Debug: Converting path coordinates...", file=sys.stderr)
        # Transformar las coordenadas del path_world de metros a lat/lon
        path_lonlat = []
        
        # Usar el punto inicial original como primer punto
        path_lonlat.append([x, y])
        
        # Transformar el resto de puntos
        for x, y in path_world[1:]:  # Empezamos desde el segundo punto
            lon, lat = transformar_coordenadas_inversa(x, y)
            path_lonlat.append([lon, lat])
            

        # Crear respuesta en formato similar a ArcGIS Polyline
        response = {
            "status": "success",
            "data": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": path_lonlat  # Lista de coordenadas [lon, lat]
                        }
                    }
                ]
            }
        }

        print(json.dumps(response))
        sys.stdout.flush()
    else:
        error_response = {
            "status": "error",
            "error": "No se generó un path válido"
        }
        print(json.dumps(error_response))
        sys.stdout.flush()
        
except Exception as e:
    error_response = {
        "status": "error",
        "error": str(e)
    }
    print(json.dumps(error_response))
    sys.exit(1)










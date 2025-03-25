from flask import Flask, render_template, request, jsonify, send_file
from shapely import wkt
import geopandas as gpd
import pandas as pd
from io import BytesIO
import zipfile	
import json
import subprocess
import psycopg2
from rasterio.io import MemoryFile
import base64
from pyproj import CRS, Transformer
import sys, os
import tempfile

app = Flask(__name__)
app.debug = True


# Conexión a la BBDD
conn = psycopg2.connect(
host="localhost",
database="b2",
user="postgres",
password="postgres"
)

# Función para sacar el valor del raster dado unas coordendas
def obtener_valor_raster(cur, esquema, tabla, x, y, layer, filename):
    try:
        
        if isinstance(layer, int):
            layer_id = layer
        else:
            cur.execute("SELECT id FROM capas WHERE name = %s", (layer,))
            layer_id = cur.fetchone()[0]

        consulta = """
        SELECT ST_Value(
            rast,
            ST_Transform(
                ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                22185
            )
        )
        FROM {}.{}
        WHERE capa_id = %s
        AND filename = %s
        AND ST_Intersects(
            rast,
            ST_Transform(
                ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                22185
            )
        );
        """.format(esquema, tabla)
            
        cur.execute(consulta, (x, y, layer_id, filename, x, y))
        resultado = cur.fetchone()
            
        if resultado is None:
            print(f"No hay intersección en las coordenadas especificadas para layer={layer}, filename={filename}")
            return None
            
        valor = resultado[0]
        return valor
    except Exception as e:
        print(f"Error en obtener_valor_raster: {e}")
        return None

# Creamos un cursor para ejecutar las consultas
cur = conn.cursor()

# Ruta principal de la página
@app.route('/map')
def map():
    try:
        # Cargar el shapefile principal
        gdf = gpd.read_file('files/BuenosAires.shp')
        gdf = gdf.to_crs(epsg=4326)
        gdf_json = gdf.to_json()
        
        # Cargar el shapefile del catastro
        try:
            catastro_gdf = gpd.read_file('files/parcelas_rec_proj.shp')
            catastro_gdf = catastro_gdf.to_crs(epsg=4326)
            catastro_gdf_json = catastro_gdf.to_json()
        except Exception as e:
            print(f"Error al cargar el shapefile del catastro: {str(e)}")
            catastro_gdf_json = None
        
        return render_template('map.html', 
                               bounds=gdf.total_bounds.tolist(), 
                               gdf=gdf_json, 
                               catastro=catastro_gdf_json)
    except Exception as e:
        print(f"Error al cargar los shapefiles: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
# Ruta que nos permite obetener los valores de los raster para añadirlos a los forms
@app.route('/get_initial_values', methods=['POST'])
def get_initial_values():
    data = request.get_json()
    x = data['lon']
    y = data['lat']
    layer_name = data['layer']
    
    # Obtenemos el id de la capa seleccionada
    cur.execute("SELECT id FROM capas WHERE name = %s", (layer_name,))
    layer_id = cur.fetchone()[0]

    # Variables comunes
    k = obtener_valor_raster(cur, "public", "rasters", x, y, layer_id, "Thermal Conductivity")
    pc = obtener_valor_raster(cur, "public", "rasters", x, y, layer_id, "Heat Capacity")

    cur.execute("SELECT pvalue FROM public.param WHERE pname = 'ThreshTem'")
    IncT = float(cur.fetchone()[0])

    cur.execute("SELECT pvalue FROM public.param WHERE pname = 'OperTime'")
    Tiempo = float(cur.fetchone()[0])  #Duración de Funcionamiento

    cur.execute("SELECT pvalue FROM public.param WHERE pname = 'HeatRate'")
    Ql = float(cur.fetchone()[0])
    
    if layer_id == 1 or layer_id == 3:
        u = obtener_valor_raster(cur, "public", "rasters", x, y, layer_id, "Darcy Velocity")
    else: 
        u = None

    initial_values = {
        'darcy_vel': u,
        'therm_cond': k,
        'thresh_temp': IncT,
        'heat_cap': pc,
        'oper_time': Tiempo,
        'heat_rate': Ql
    }
    
    return jsonify(initial_values)

# Ruta para obtener la gráfica TCC o la pluma
@app.route('/map/click', methods=['POST'])
def map_click():
    data = request.get_json()
    mode = data.get('mode')
    print(f"Modo seleccionado: {mode}")
    if mode == 'tiger':
        x = data['lon']
        y = data['lat']
        layer_name = data['layer']
        darcy_vel = data['darcy_vel']
        therm_cond = data['therm_cond']
        thresh_temp = data['thresh_temp']
        heat_cap = data['heat_cap']
        oper_time = data['oper_time']

        # Obtenemos el id de la capa seleccionada
        cur.execute("SELECT id FROM capas WHERE name = %s", (layer_name,))
        layer_id = cur.fetchone()[0]

        #Obtenemos el tag de la capa seleccionada
        cur.execute("SELECT tag FROM capas WHERE name = %s", (layer_name,))
        layer_tag = cur.fetchone()[0]

        if layer_tag == "Aquifer":
            lalpha = obtener_valor_raster(cur, "public", "rasters", x, y, layer_id, "LAlpha")
            talpha = obtener_valor_raster(cur, "public", "rasters", x, y, layer_id, "TAlpha")
        else: 
            lalpha = None
            talpha = None

        print(f"Coordenadas: {x}, {y}, Capa: {layer_name}")
        print(f"Parámetros: Vel. Darcy: {darcy_vel}, Cond. Térmica: {therm_cond}, "
            f"Umb. Temperatura: {thresh_temp}, Cap. Calorífica: {heat_cap}, "
            f"T. Duración: {oper_time}")
        print(f"LAlpha: {lalpha}, TAlpha: {talpha}, Layer Tag: {layer_tag}")
        
        try:
            # Prepare command arguments
            command = [
                'python', 'scripts/TCC.py', 
                str(x), str(y), layer_name, 
                                    str(darcy_vel), str(therm_cond), str(thresh_temp), 
                str(heat_cap), str(oper_time)
            ]
            
            # Add optional parameters if available
            if lalpha is not None:
                command.append(str(lalpha))
            else:
                command.append("None")
                
            if talpha is not None:
                command.append(str(talpha))
            else: 
                command.append("None")
                
            command.append(str(layer_tag))
            
            print(f"Executing command: {' '.join(command)}")
            
            # Execute TCC.py with the command
            result = subprocess.run(
                command,
                capture_output=True, 
                text=True
            )
            
            # Check for errors
            if result.returncode != 0:
                print(f"Error executing TCC.py. Return code: {result.returncode}")
                print(f"Standard error: {result.stderr}")
                return jsonify({
                    'error': 'Error executing TCC.py',
                    'stderr': result.stderr,
                    'command': ' '.join(command)
                }), 500
            
            # Parse the output
            try:
                tcc_result = json.loads(result.stdout)
                return jsonify(tcc_result)
            except json.JSONDecodeError:
                print(f"Failed to parse JSON output from TCC.py: {result.stdout}")
                return jsonify({
                    'error': 'Invalid JSON returned from TCC.py',
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'command': ' '.join(command)
                }), 500
            
        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            print(f"Exception executing TCC.py: {str(e)}\n{traceback_str}")
            return jsonify({
                'error': str(e),
                'traceback': traceback_str,
                'message': 'Error al ejecutar TCC.py'
            }), 500
        except subprocess.CalledProcessError as e:
            return jsonify({'error': str(e), 'message': 'Error al ejecutar TCC.py'}), 500
        
    elif mode == 'rester':
        try:
            data = request.get_json()
            print(f"Datos recibidos en /map/click: {data}")

            x = data['lon']
            y = data['lat']
            layer_name = data['layer']
            heat_rate = float(data['heat_rate'])  # Ensure numeric conversion
            therm_cond = float(data['therm_cond'])
            thresh_temp = float(data['thresh_temp'])
            heat_cap = float(data['heat_cap'])
            oper_time = float(data['oper_time'])

            # Obtenemos el id de la capa seleccionada
            cur.execute("SELECT id FROM capas WHERE name = %s", (layer_name,))
            layer_id = cur.fetchone()[0]

            #Obtenemos el tag de la capa seleccionada
            cur.execute("SELECT tag FROM capas WHERE name = %s", (layer_name,))
            layer_tag = cur.fetchone()[0]

            if layer_id == 1 or layer_id == 3:
                darcy_vel = float(data['darcy_vel'])  # Ensure numeric conversion
                lalpha = obtener_valor_raster(cur, "public", "rasters", x, y, layer_id, "LAlpha")
                talpha = obtener_valor_raster(cur, "public", "rasters", x, y, layer_id, "TAlpha")
            else: 
                darcy_vel = None
                lalpha = None
                talpha = None

            print(f"Coordenadas: {x}, {y}, Capa: {layer_name}")
            print(f"Parámetros: Vel. Darcy: {darcy_vel}, Heat Rate: {heat_rate}, Cond. Térmica: {therm_cond}, "
                  f"Umb. Temperatura: {thresh_temp}, Cap. Calorífica: {heat_cap}, "
                  f"T. Duración: {oper_time}")
            
            
            if layer_id == 1 or layer_id == 3:
                # Primero calculamos la línea de flujo
                try:
                    flow_command = ['python', 'scripts/prueba.py', str(x), str(y), str(layer_id)]
                    print(f"Executing flow command: {' '.join(flow_command)}")
                    
                    flow_result = subprocess.run(
                        flow_command,
                        capture_output=True, 
                        text=True,
                        check=True  # This will raise an exception if the process returns non-zero
                    )
                    
                    print(f"Resultado línea de flujo (stdout): {flow_result.stdout}")
                    print(f"Resultado línea de flujo (stderr): {flow_result.stderr}")
                
                    flow_feature = None
                    try:
                        flow_path = json.loads(flow_result.stdout)
                        if flow_path["status"] == "success":
                            flow_feature = flow_path["data"]["features"][0]
                    except json.JSONDecodeError as e:
                        print(f"Error al decodificar la salida de prueba.py:")
                        print(f"stdout: {flow_result.stdout[:500]}...")
                        print(f"stderr: {flow_result.stderr[:500]}...")
                        # Continue without flow feature
                        flow_feature = None
                
                except subprocess.CalledProcessError as e:
                    print(f"Error executing prueba.py: {str(e)}")
                    print(f"stderr: {e.stderr}")
                    # Continue without flow feature
                    flow_feature = None
            else: 
                flow_feature = None
                
            # Now proceed with plume calculation
            try:
                plume_command = [
                    'python', 'scripts/plume.py',
                    str(x), str(y), layer_name,
                    str(darcy_vel) if darcy_vel is not None else '0',
                    str(heat_rate), str(therm_cond), str(thresh_temp),
                    str(heat_cap), str(oper_time), 
                    str(lalpha) if lalpha is not None else 'None', 
                    str(talpha) if talpha is not None else 'None',
                    'null' if flow_feature is None else json.dumps(flow_feature)
                ]
                
                print(f"Executing plume command: {' '.join(plume_command)}")
                
                plume_result = subprocess.run(
                    plume_command,
                    capture_output=True, 
                    text=True,
                    check=True
                )

                print(f"Resultado pluma (stdout): {plume_result.stdout}")
                print(f"Resultado pluma (stderr): {plume_result.stderr}")
                
                try:
                    plume = json.loads(plume_result.stdout)
                    
                    # Combinar resultados
                    response = {'plume': plume}
                    return jsonify(response)
                    
                except json.JSONDecodeError as e:
                    print(f"Error al decodificar la salida de plume.py:")
                    print(f"stdout: {plume_result.stdout[:500]}...")
                    print(f"stderr: {plume_result.stderr[:500]}...")
                    return jsonify({
                        'error': 'Error parsing plume output',
                        'stdout': plume_result.stdout,
                        'stderr': plume_result.stderr
                    }), 500
            
            except subprocess.CalledProcessError as e:
                print(f"Error executing plume.py: {str(e)}")
                print(f"stderr: {e.stderr}")
                return jsonify({
                    'error': 'Error executing plume.py',
                    'stderr': e.stderr
                }), 500
                
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"Error: {e}")
            print(error_traceback)
            return jsonify({
                'error': str(e),
                'traceback': error_traceback
            }), 500

# Ruta para obtener los rasters (nombres) de las distintas capas
@app.route('/get_rasters/<layer>')
def get_rasters(layer):
    try:
        # Obtener el ID de la capa
        cur.execute("SELECT id FROM capas WHERE name = %s", (layer,))
        layer_id = cur.fetchone()
        
        if layer_id is None:
            return jsonify({"error": "Capa no encontrada"}), 404

        layer_id = layer_id[0]

        # Obtener los nombres de los rasters asociados a esta capa
        cur.execute("SELECT DISTINCT filename FROM rasters WHERE capa_id = %s", (layer_id,))
        rasters = [row[0] for row in cur.fetchall()]

        return jsonify(rasters)
    except Exception as e:
        print(f"Error al obtener rasters: {e}")
        return jsonify({"error": str(e)}), 500
    
# Ruta para obtener los rasters (valores) de las distintas capas
@app.route('/get_raster/<layer>/<filename>')
def get_raster(layer, filename):
    try:
        # Obtener el ID de la capa
        cur.execute("SELECT id FROM capas WHERE name = %s", (layer,))
        layer_id = cur.fetchone()
        if layer_id is None:
            return jsonify({"error": "Layer not found"}), 404
        layer_id = layer_id[0]

        # Obtener los datos del raster de la base de datos
        cur.execute("""
            SELECT ST_AsTIFF(ST_Union(rast)) as tiff,
                   ST_Envelope(ST_Union(rast)) as envelope
            FROM rasters 
            WHERE capa_id = %s AND filename = %s
        """, (layer_id, filename))
        
        raster_part = cur.fetchone()
        
        if not raster_part:
            return jsonify({"error": "Raster not found"}), 404

        # Leer el raster desde los datos TIFF
        with MemoryFile(raster_part[0]) as memfile:
            with memfile.open() as dataset:
                # Obtener información sobre el raster
                print(f"Raster size: {dataset.width} x {dataset.height}")
                print(f"Raster bounds: {dataset.bounds}")
                print(f"Raster transform: {dataset.transform}")
                
                # Obtener los límites del raster
                bounds = dataset.bounds
            
            # Leer los datos del raster como bytes
            raster_bytes = memfile.read()

        # Convertir los límites de EPSG:22185 a EPSG:4326
        transformer = Transformer.from_crs(CRS.from_epsg(22185), CRS.from_epsg(4326), always_xy=True)
        bounds_4326 = transformer.transform_bounds(*bounds)

        # Obtener los valores mínimo y máximo del raster
        cur.execute("""
            SELECT MIN((ST_SummaryStats(rast)).min) as min_value,
                   MAX((ST_SummaryStats(rast)).max) as max_value
            FROM rasters 
            WHERE capa_id = %s AND filename = %s
        """, (layer_id, filename))
        
        min_max = cur.fetchone()
        min_value, max_value = min_max[0], min_max[1]

        return jsonify({
            "rasterData": base64.b64encode(raster_bytes).decode(),
            "bounds": bounds_4326,
            "minValue": min_value,
            "maxValue": max_value
        })

    except Exception as e:
        app.logger.error(f"Error processing raster request: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    

# Ruta para obtener las capas
@app.route('/get_layers')
def get_layers():
    print("Función get_layers llamada")
    try:
        cur.execute("SELECT name, tag FROM capas ORDER BY id")
        layers = cur.fetchall()
        print(f"Capas obtenidas: {layers}")
        return jsonify([{"name": layer[0], "tag": layer[1]} for layer in layers])
    except Exception as e:
        print(f"Error al obtener las capas: {e}")
        return jsonify({"error": str(e)}), 500

# Ruta para poder guardar las plumas (individuales) en formato .shp
@app.route('/save_shapefile', methods=['POST'])
def save_shapefile():
    print("Iniciando función save_shapefile")
    geojson_data = request.get_json()
    print(f"GeoJSON recibido: {json.dumps(geojson_data, indent=2)}")

    try:
        # Separar las características en polígonos y puntos
        polygon_features = [f for f in geojson_data['features'] if f['geometry']['type'] == 'Polygon']
        point_features = [f for f in geojson_data['features'] if f['geometry']['type'] == 'Point']

        # Crear GeoDataFrames separados
        gdf_polygon = gpd.GeoDataFrame.from_features(polygon_features)
        gdf_point = gpd.GeoDataFrame.from_features(point_features)

        # Añadir la información adicional solo al polígono
        if 'information' in geojson_data['features'][0]:
            information = geojson_data['features'][0]['information']
            for key, value in information.items():
                gdf_polygon[key] = value

        # Asignar CRS
        gdf_polygon.crs = CRS.from_epsg(4326)
        gdf_point.crs = CRS.from_epsg(4326)

        print(f"GeoDataFrame polígono creado: {gdf_polygon.head()}")
        print(f"GeoDataFrame punto creado: {gdf_point.head()}")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Guardar polígono
            polygon_base = os.path.join(tmpdir, 'pluma_polygon')
            gdf_polygon.to_file(f"{polygon_base}.shp", driver='ESRI Shapefile')

            # Guardar punto
            point_base = os.path.join(tmpdir, 'pluma_point')
            gdf_point.to_file(f"{point_base}.shp", driver='ESRI Shapefile')

            # Crear ZIP con ambos shapefiles
            mem_zip = BytesIO()
            with zipfile.ZipFile(mem_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                for base in [polygon_base, point_base]:
                    for ext in ['.shp', '.shx', '.dbf', '.prj']:
                        file_path = f"{base}{ext}"
                        if os.path.exists(file_path):
                            zf.write(file_path, os.path.basename(file_path))
                            print(f"Archivo añadido al ZIP: {file_path}")

            mem_zip.seek(0)

            return send_file(
                mem_zip,
                mimetype='application/zip',
                as_attachment=True,
                download_name='pluma.zip'
            )

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"Error al guardar el shapefile: {str(e)}")
        print(f"Traceback completo:\n{error_traceback}")
        return jsonify({"error": f"Error al guardar el shapefile: {str(e)}"}), 500
    
# Ruta para poder guardar las plumas (todas las dibujadas) en formato .shp
@app.route('/save_all_plumes', methods=['POST'])
def save_all_plumes():
    try:
        geojson_data = request.get_json()
        print("GeoJSON recibido:", json.dumps(geojson_data, indent=2))

        # Separar las características en polígonos y puntos
        polygon_features = []
        point_features = []
        
        for feature in geojson_data['features']:
            if feature['geometry']['type'] == 'Polygon':
                # Asegurarse de que todas las propiedades necesarias estén en el nivel superior
                properties = feature.get('properties', {})
                if 'information' in feature:
                    properties.update(feature['information'])
                feature['properties'] = properties
                polygon_features.append(feature)
            elif feature['geometry']['type'] == 'Point':
                point_features.append(feature)

        # Crear GeoJSON separados para polígonos y puntos
        polygon_geojson = {
            "type": "FeatureCollection",
            "features": polygon_features
        }
        
        point_geojson = {
            "type": "FeatureCollection",
            "features": point_features
        }

        # Crear GeoDataFrames
        if polygon_features:
            gdf_polygon = gpd.GeoDataFrame.from_features(polygon_geojson)
            gdf_polygon.set_crs(epsg=4326, inplace=True)
        else:
            raise ValueError("No hay plumas para guardar")

        if point_features:
            gdf_point = gpd.GeoDataFrame.from_features(point_geojson)
            gdf_point.set_crs(epsg=4326, inplace=True)

        print("Columnas del GeoDataFrame de polígonos:", gdf_polygon.columns)
        if point_features:
            print("Columnas del GeoDataFrame de puntos:", gdf_point.columns)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Guardar polígonos (plumas)
            polygon_base = os.path.join(tmpdir, 'todas_las_plumas')
            gdf_polygon.to_file(f"{polygon_base}.shp", driver='ESRI Shapefile')
            print(f"Shapefile de polígonos guardado en: {polygon_base}.shp")

            # Guardar puntos si existen
            if point_features:
                point_base = os.path.join(tmpdir, 'puntos_de_plumas')
                gdf_point.to_file(f"{point_base}.shp", driver='ESRI Shapefile')
                print(f"Shapefile de puntos guardado en: {point_base}.shp")

            # Crear ZIP con los shapefiles
            mem_zip = BytesIO()
            with zipfile.ZipFile(mem_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Siempre incluir el shapefile de polígonos
                for ext in ['.shp', '.shx', '.dbf', '.prj']:
                    file_path = f"{polygon_base}{ext}"
                    if os.path.exists(file_path):
                        zf.write(file_path, os.path.basename(file_path))
                        print(f"Archivo añadido al ZIP: {file_path}")

                # Incluir el shapefile de puntos si existe
                if point_features:
                    for ext in ['.shp', '.shx', '.dbf', '.prj']:
                        file_path = f"{point_base}{ext}"
                        if os.path.exists(file_path):
                            zf.write(file_path, os.path.basename(file_path))
                            print(f"Archivo añadido al ZIP: {file_path}")

            mem_zip.seek(0)

            return send_file(
                mem_zip,
                mimetype='application/zip',
                as_attachment=True,
                download_name='todas_las_plumas.zip'
            )

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"Error al guardar todas las plumas: {str(e)}")
        print(f"Traceback completo:\n{error_traceback}")
        return jsonify({"error": f"Error al guardar todas las plumas: {str(e)}"}), 500
    

if __name__ == '__main__':
    app.run(debug=True)

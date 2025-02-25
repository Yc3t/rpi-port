import serial
import time
from datetime import datetime
import pynmea2
import os
from pymongo import MongoClient
import logging
from uart import UARTReceiver
from enum import Enum

## Log level
class LogLevel(str, Enum):
    INFO = "info"
    DEBUG = "debug"

class CombinedTracker(UARTReceiver):
    def __init__(
        self,
        gps_port="COM26",
        ble_port="COM20",
        ble_baudrate=115200,
        gps_baudrate=115200,
        mongo_uri="mongodb://localhost:27017/",
        log_level="info"
    ):
        """Inicializa el tracker"""
        # Configurar logging
        self.log_level = log_level.lower()
        self._setup_logging()
        self.logger.info("Iniciando rastreador combinado GPS + BLE")

        # Inicializar receptor UART BLE
        super().__init__(port=ble_port, baudrate=ble_baudrate)

        # Configuración MongoDB
        self.client = MongoClient(mongo_uri)
        self.db = self.client.tracking_data
        self.collection = self.db.portfinal

        # Configuración GPS
        self.gps_port = gps_port
        self.gps_baudrate = gps_baudrate
        self.last_gps_data = None
        
        try:
            self.gps_ser = serial.Serial(self.gps_port, self.gps_baudrate, timeout=1)
            self.logger.info(f"GPS conectado en {self.gps_port}")
        except serial.SerialException as e:
            self.logger.error(f"Error conectando GPS: {e}")
            raise

        # Formato del buffer BLE
        self.HEADER_MAGIC = b"\x55\x55\x55\x55"
        self.HEADER_FORMAT = {
            "header": 4,
            "sequence": 1,
            "n_adv_raw": 2,
            "n_mac": 1,
        }

        self.DEVICE_FORMAT = {
            "mac": 6,
            "addr_type": 1,
            "adv_type": 1,
            "rssi": 1,
            "data_len": 1,
            "data": 31,
            "n_adv": 1,
        }

        self.HEADER_LENGTH = sum(self.HEADER_FORMAT.values())
        self.DEVICE_LENGTH = sum(self.DEVICE_FORMAT.values())

    def _setup_logging(self):
        """Configura el sistema de logging"""
        # Crear directorio de logs si no existe
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Nombre del archivo de log con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"tracker_{timestamp}.log")

        # Configurar logging
        self.logger = logging.getLogger("GPS_BLE_Tracker")
        self.logger.setLevel(logging.DEBUG)

        # Handler para archivo
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG if self.log_level == "debug" else logging.INFO)

        # Handler para consola con más información
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)  # Cambiar a DEBUG para ver más detalles

        # Formato detallado para consola
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | Buffer: %(message)s'
        )
        console_handler.setFormatter(console_formatter)

        # Formato del log
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)



        # Agregar handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def _parse_gps(self):
        """Parsea datos GPS"""
        try:
            while self.gps_ser.in_waiting:  # Read all available GPS data
                line = self.gps_ser.readline().decode('ascii', errors='replace')
                
                if line.startswith("$GPRMC"):
                    msg = pynmea2.parse(line)
                    if msg.status == 'A':  # Solo almacena si el estado es válido
                        self.last_gps_data = {
                            "coordinates": {
                                "longitude": msg.longitude if msg.longitude else None,
                                "latitude": msg.latitude if msg.latitude else None,
                            },
                            "speed": msg.spd_over_grnd if msg.spd_over_grnd else 0,
                            "track_valid": True
                        }
                        return self.last_gps_data  # Return the most recent GPS data
                    
        except Exception as e:
            self.logger.error(f"Error parseando GPS: {e}")
        return self.last_gps_data  # Return last known position if no new data

    def _store_buffer(self, header, devices):
        """Almacena el buffer BLE y datos GPS en MongoDB"""
        try:
            # Obtener datos GPS actuales
            gps_data = self._parse_gps() or self.last_gps_data

            document = {
                'timestamp': datetime.now(),
                'sequence': header['sequence'],
                'n_adv_raw': header['n_adv_raw'],
                'n_mac': header['n_mac'],
                'devices': [],
                'gps_data': gps_data
            }

            for device in devices:
                device_doc = {
                    'mac': device['mac'],
                    'addr_type': device['addr_type'],
                    'adv_type': device['adv_type'],
                    'rssi': device['rssi'],
                    'data_len': device['data_len'],
                    'data': device['data'].hex(),
                    'n_adv': device['n_adv']
                }
                document['devices'].append(device_doc)
            
            result = self.collection.insert_one(document)
            self.logger.debug(f"Buffer combinado almacenado - ID: {result.inserted_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error almacenando en BD: {e}")
            return False

    def receive_messages(self, duration=None):
        """Recibe y almacena buffers BLE con datos GPS"""
        self.logger.info("=== Iniciando recepción de buffers combinados ===")
        start_time = time.time()
        buffers_procesados = 0
        
        while True:
            try:
                # Verificar tiempo transcurrido
                if duration and (time.time() - start_time) >= duration:
                    self.logger.info(f"Tiempo de ejecución ({duration}s) completado")
                    self.logger.info(f"Total de buffers procesados: {buffers_procesados}")
                    break

                # Update GPS data 
                self._parse_gps()

                # Busca la cabecera BLE
                while True:
                    if self.serial.read() == b'\x55':
                        potential_header = b'\x55' + self.serial.read(3)
                        if potential_header == self.HEADER_MAGIC:
                            self.logger.debug("Cabecera UART encontrada")
                            break

                # Lee y parsea la cabecera
                header_data = potential_header + self.serial.read(self.HEADER_LENGTH - 4)
                header = self._parse_header(header_data)
                
                if not header:
                    self.logger.warning("Error al parsear cabecera")
                    continue

                # Lee todos los dispositivos
                devices = []
                for i in range(header['n_mac']):
                    device_data = self.serial.read(self.DEVICE_LENGTH)
                    device = self._parse_device(device_data)
                    if device:
                        devices.append(device)

                # Procesa el buffer si hay dispositivos
                if devices:
                    # Obtener datos GPS actuales
                    gps_data = self._parse_gps() or self.last_gps_data
                    
                    # Crear resumen de dispositivos
                    devices_summary = [
                        f"{dev['mac']}(RSSI:{dev['rssi']}dB)" 
                        for dev in devices[:3]
                    ]
                    if len(devices) > 3:
                        devices_summary.append(f"... +{len(devices)-3} más")

                    # Log detallado en consola
                    status_msg = (
                        f"\n"
                        f"├─ Secuencia: #{header['sequence']}\n"
                        f"├─ Dispositivos: {len(devices)} ({', '.join(devices_summary)})\n"
                        f"├─ Anuncios raw: {header['n_adv_raw']}\n"
                        f"└─ GPS: {'✓' if gps_data else '✗'}"
                    )
                    
                    if gps_data and gps_data.get('coordinates'):
                        status_msg += (
                            f"\n   └─ Pos: {gps_data['coordinates']['latitude']:.6f}, "
                            f"{gps_data['coordinates']['longitude']:.6f} "
                            f"({gps_data.get('speed', 0):.2f} knots)"
                        )
                    
                    self.logger.info(status_msg)
                    
                    # Almacenar en MongoDB
                    if self._store_buffer(header, devices):
                        buffers_procesados += 1

            except KeyboardInterrupt:
                self.logger.info("\n=== Captura interrumpida por el usuario ===")
                self.logger.info(f"Total de buffers procesados: {buffers_procesados}")
                break
            except Exception as e:
                self.logger.error(f"Error inesperado: {e}")
                continue

    def close(self):
        """Cierra todas las conexiones"""
        try:
            super().close()  # Cierra UART BLE
            if hasattr(self, 'gps_ser'):
                self.gps_ser.close()
                self.logger.info("Conexión GPS cerrada")
            self.client.close()
            self.logger.info("Conexión MongoDB cerrada")
        except Exception as e:
            self.logger.error(f"Error al cerrar conexiones: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rastreador combinado GPS + BLE")
    parser.add_argument(
        "--gps-port", type=str, default="COM26", help="Puerto GPS (default: COM26)"
    )
    parser.add_argument(
        "--ble-port", type=str, default="COM20", help="Puerto BLE (default: COM20)"
    )
    parser.add_argument("--duration", type=int, help="Duración del rastreo en segundos")
    parser.add_argument(
        "--mongo-uri",
        type=str,
        default="mongodb://localhost:27017/",
        help="URI de MongoDB (default: mongodb://localhost:27017/)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["info", "debug"],
        default="info",
        help="Nivel de logging (default: info)"
    )

    args = parser.parse_args()

    try:
        tracker = CombinedTracker(
            gps_port=args.gps_port, 
            ble_port=args.ble_port, 
            mongo_uri=args.mongo_uri,
            log_level=args.log_level
        )
        tracker.logger.info(
            "Iniciando captura %s", 
            "indefinida" if not args.duration else f"por {args.duration} segundos"
        )
        tracker.receive_messages(duration=args.duration)
    except Exception as e:
        if hasattr(tracker, "logger"):
            tracker.logger.error(f"Error: {e}")
        else:
            print(f"Error: {e}")
    finally:
        if hasattr(tracker, "close"):
            tracker.close()


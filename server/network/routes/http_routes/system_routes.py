from flask import jsonify, request
import psutil
import time

class SystemRoutes:
    def __init__(self, app):
        self.app = app
        self.register_routes()
        
        self.system_info = SystemInfo()

    def register_routes(self):
        # 仪表盘
        """由于前端采用 vue3 重构，该接口返回内容由前端自行实现，故该接口不写"""
        # @self.app.route('/system_manager/dashboard',methods=['GET'])

        # 系统信息
        @self.app.route('/system_manager/system_info', methods=['GET'])
        def system_info():
            """获取系统信息"""
            try:
                # 创建静态变量存储上次的值
                if not hasattr(system_info, 'last_bytes'):
                    self.system_info.last_bytes = {
                        'sent': 0,
                        'recv': 0,
                        'time': time.time()
                    }

                # 一次性获取所有系统信息
                cpu_percent = psutil.cpu_percent()
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                net = psutil.net_io_counters()
                current_time = time.time()

                # 计算网络速度
                time_delta = current_time - self.system_info.last_bytes['time']
                bytes_sent_diff = net.bytes_sent - self.system_info.last_bytes['sent']
                bytes_recv_diff = net.bytes_recv - self.system_info.last_bytes['recv']

                # 转换为 KB/s
                upload_speed = (bytes_sent_diff / time_delta) / 1024
                download_speed = (bytes_recv_diff / time_delta) / 1024

                # 更新网络数据
                self.system_info.last_bytes = {
                    'sent': net.bytes_sent,
                    'recv': net.bytes_recv,
                    'time': current_time
                }

                # 构建返回数据
                BYTES_TO_GB = 1024 ** 3
                return jsonify({
                    'status': 'success',
                   'message': '获取系统信息成功',
                    'data': {
                       'cpu_percent': cpu_percent,
                       'memory': {
                           'total': round(memory.total / BYTES_TO_GB,2),
                           'used':  round(memory.used / BYTES_TO_GB, 2),
                           'percent': memory.percent
                       },
                       'disk': {
                           'total': round(disk.total / BYTES_TO_GB, 2),
                           'used':  round(disk.used / BYTES_TO_GB, 2),
                           'percent': disk.percent
                       },
                       'network': {
                           'upload':round(upload_speed, 2),
                           'download':  round(download_speed, 2)
                       }
                   }
                }), 200
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500

        # # 检查更新 TODO： 此接口待项目完全重构后实现
        # @self.app.route('/system_manager/check_update',methods=['GET'])

        # # 确认更新
        # @self.app.route('/system_manager/confirm_update',methods=['POST'])

        # # 检查依赖
        # @self.app.route('/system_manager/check_dependencies',methods=['GET'])

        # # 安装依赖 /install_dependencies
        # @self.app.route('/system_manager/install_dependencies',methods=['POST'])




class SystemInfo:
    def __init__(self):
        self.cpu_percent = 0
        self.memory = {
            'total': 0,
            'used': 0,
            'percent': 0
        }
        self.disk = {
            'total': 0,
            'used': 0,
            'percent': 0
        }
        self.network = {
            'upload': 0,
            'download': 0
        }
        self.last_bytes = {
            'sent': 0,
            'recv': 0,
            'time': 0
        }

    def update(self, cpu_percent, memory, disk, network):
        self.cpu_percent = cpu_percent
        self.memory = memory
        self.disk = disk
        self.network = network
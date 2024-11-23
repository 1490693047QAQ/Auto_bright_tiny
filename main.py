import os
import time
import json
import numpy as np
from scipy.optimize import curve_fit

# 配置参数

def find_backlight_path():
    """
    自动寻找有效的 BACKLIGHT_PATH。
    返回第一个找到的 backlight 控制路径，如果没有找到，则返回 None。
    """
    base_path = "/sys/class/backlight"
    
    if not os.path.exists(base_path):
        print("Backlight path not found.")
        return None

    # 获取所有子目录
    candidates = [os.path.join(base_path, entry) for entry in os.listdir(base_path)]
    for candidate in candidates:
        brightness_file = os.path.join(candidate, "brightness")
        max_brightness_file = os.path.join(candidate, "max_brightness")
        
        # 检查是否存在控制亮度的文件
        if os.path.exists(brightness_file) and os.path.exists(max_brightness_file):
            # print(f"Backlight path found: {candidate}")
            return candidate
    
    print("No valid backlight path found.")
    return None

def find_main():
    backlight_path = find_backlight_path()
    if backlight_path:
        brightness_file = os.path.join(backlight_path, "brightness")
        max_brightness_file = os.path.join(backlight_path, "max_brightness")
        
        # 读取当前亮度和最大亮度
        with open(brightness_file, 'r') as bf:
            current_brightness = int(bf.read().strip())
        with open(max_brightness_file, 'r') as mbf:
            max_brightness = int(mbf.read().strip())

        print(f"Current Brightness: {current_brightness}")
        print(f"Max Brightness: {max_brightness}")
    else:
        print("Unable to control screen brightness.")

SENSOR_PATH = "/sys/bus/iio/devices/iio:device0/in_illuminance_raw"
BACKLIGHT_PATH = str(find_backlight_path()) + '/brightness'
MAX_BRIGHTNESS_PATH = str(find_backlight_path()) + '/max_brightness'

BRIGHTNESS_MIN = 0
BRIGHTNESS_MAX = 255
SENSOR_MAX_LUX = 1000
ADJUST_INTERVAL = 0.5
USER_ADJUST_THRESHOLD = 5

PREFERENCES_FILE = "brightness_data.json"  # 存储历史数据点的文件

# 全局变量
brightness_data = []  # 历史数据点列表 [(lux, brightness)]
previous_brightness = None


def read_sensor():
    try:
        with open(SENSOR_PATH, "r") as f:
            lux = int(f.read().strip())
        return lux
    except (FileNotFoundError, ValueError):
        return None


def get_current_brightness():
    try:
        with open(BACKLIGHT_PATH, "r") as f:
            brightness = int(f.read().strip())
        return brightness
    except (FileNotFoundError, ValueError):
        return None


def write_brightness(brightness):
    try:
        with open(BACKLIGHT_PATH, "w") as f:
            f.write(str(brightness))
    except PermissionError:
        print(f"需要 root 权限写入亮度: {BACKLIGHT_PATH}")


def load_preferences():
    """加载用户历史数据点"""
    global brightness_data
    if os.path.exists(PREFERENCES_FILE):
        with open(PREFERENCES_FILE, "r") as f:
            brightness_data = json.load(f)


def save_preferences():
    """保存用户历史数据点"""
    global brightness_data
    with open(PREFERENCES_FILE, "w") as f:
        json.dump(brightness_data, f, indent=4)


def brightness_function(lux, a, b, c):
    """
    自定义亮度函数，用于拟合 (二次函数作为示例)
    brightness = a * lux^2 + b * lux + c
    """
    return a * lux**2 + b * lux + c


def calculate_brightness(lux):
    """根据环境光强度计算亮度，使用拟合的函数"""
    if lux is None:
        return None

    # 如果没有用户偏好数据，使用默认线性映射
    if not brightness_data:
        lux = min(max(lux, 0), SENSOR_MAX_LUX)
        return int(BRIGHTNESS_MIN + (lux / SENSOR_MAX_LUX) * (BRIGHTNESS_MAX - BRIGHTNESS_MIN))

    # 确保拟合的输入数据为一维数组
    lux_values, brightness_values = zip(*brightness_data)
    lux_values = np.array(lux_values)
    brightness_values = np.array(brightness_values)

    # 打印调试信息：确保是二维数组
    # print("lux_values:", lux_values)
    # print("brightness_values:", brightness_values)

    try:
        # 拟合用户偏好数据点
        params, _ = curve_fit(brightness_function, lux_values, brightness_values, maxfev=10000)

        # 使用拟合的函数计算亮度
        brightness = brightness_function(lux, *params)
        return int(round(min(max(brightness, BRIGHTNESS_MIN), BRIGHTNESS_MAX)))
    except RuntimeError as e:
        # print(f"拟合失败，使用默认逻辑: {e}")
        return int(BRIGHTNESS_MIN + (lux / SENSOR_MAX_LUX) * (BRIGHTNESS_MAX - BRIGHTNESS_MIN))
    except TypeError as w:
        # print(f"拟合失败，使用默认逻辑: {w}")
        return int(BRIGHTNESS_MIN + (lux / SENSOR_MAX_LUX) * (BRIGHTNESS_MAX - BRIGHTNESS_MIN))


def update_preferences(sensor_value, user_brightness):
    """更新用户数据点并保存"""
    global brightness_data

    # 添加新数据点
    brightness_data.append((sensor_value, user_brightness))

    # 防止数据过多，只保留最新的 100 个点
    if len(brightness_data) > 100:
        brightness_data.pop(0)

    save_preferences()


def main():
    """主程序逻辑"""
    global previous_brightness

    # 加载用户历史数据点
    load_preferences()

    # 获取最大亮度
    try:
        with open(MAX_BRIGHTNESS_PATH, "r") as f:
            max_brightness = int(f.read().strip())
        global BRIGHTNESS_MAX
        BRIGHTNESS_MAX = min(BRIGHTNESS_MAX, max_brightness)
    except FileNotFoundError:
        print(f"最大亮度路径未找到: {MAX_BRIGHTNESS_PATH}")
        return

    print("开始根据环境光调整亮度，支持学习用户习惯...")

    while True:
        lux = read_sensor()
        if lux is None:
            time.sleep(ADJUST_INTERVAL)
            continue

        # 计算目标亮度和当前亮度
        target_brightness = calculate_brightness(lux)
        current_brightness = get_current_brightness()

        # 检测用户手动调整亮度
        if (
            current_brightness is not None
            and previous_brightness is not None
            and abs(current_brightness - previous_brightness) > USER_ADJUST_THRESHOLD
        ):
            print(f"检测到用户调整亮度: {current_brightness}，记录用户偏好")
            update_preferences(lux, current_brightness)
            previous_brightness = current_brightness
            time.sleep(5)
            continue

        # 自动调整亮度
        if target_brightness is not None and target_brightness != current_brightness:
            print(f"传感器值: {lux} -> 自动调整亮度: {target_brightness}")
            write_brightness(target_brightness)
            previous_brightness = target_brightness

        time.sleep(ADJUST_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序已退出")

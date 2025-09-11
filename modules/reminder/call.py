import logging
import time
import win32gui
import pygame
from wxauto import WeChat
from wxauto.elements import ChatWnd
from uiautomation import ControlFromHandle

logger = logging.getLogger('main')

# --- 配置参数 ---
'''
如果你不知道这个是什么，请不要修改，该配置仅是为了后续可能适应新的 wx 版本而设置
'''
CALL_WINDOW_CLASSNAME = 'AudioWnd'
CALL_WINDOW_NAME = '微信'
CALL_BUTTON_NAME = '语音聊天'
HANG_UP_BUTTON_NAME = '挂断'
HANG_UP_BUTTON_LABEL = '挂断'
REFUSE_MSG = '对方已拒绝'
CALL_TIME_OUT = 15


# --- 启动语音通话 ---
def CallforWho(wx: WeChat, who: str) -> tuple[int|None, bool]:
    """
    对指定对象发起语音通话请求。

    Args:
        wx: 微信应用实例。
        who: 通话对象。

    Returns:
        若拨号成功，返回元组 (句柄号, True)。
        否则返回 (None, False)。
    """
    logger.info("尝试发起语音通话")
    try:
        if win32gui.FindWindow('ChatWnd', who):
            # --- 若找到了和指定对象的独立聊天窗口，在这个窗口上操作 ---
            try:
                chat_wnd = ChatWnd(who, wx.language)
                chat_wnd._show()
                voice_call_button = chat_wnd.UiaAPI.ButtonControl(Name=CALL_BUTTON_NAME)
                if voice_call_button.Exists(1):
                    voice_call_button.Click()
                    logger.info("已发起通话")
                    time.sleep(0.5) 
                    hWnd = win32gui.FindWindow(CALL_WINDOW_CLASSNAME, CALL_WINDOW_NAME)
                    return hWnd, True
                else:
                    logger.error("发起通话时发生错误：找不到通话按钮")
                    return None, False

            except Exception as e:
                logger.error(f"发起通话时发生错误: {e}")
                return None, False

        else:
            # --- 未找到独立窗口，需要进入主页面操作 ---
            wx._show()
            wx.ChatWith(who)
            try:
                chat_box = wx.ChatBox
                if not chat_box.Exists(1):
                    logger.error("未找到聊天页面")
                    return None, False
                voice_call_button = None
                voice_call_button = chat_box.ButtonControl(Name=CALL_BUTTON_NAME)
                if voice_call_button.Exists(1):
                    voice_call_button.Click()
                    logger.info("已发起通话")
                    hWnd = win32gui.FindWindow(CALL_WINDOW_CLASSNAME, CALL_WINDOW_NAME)
                    return hWnd, True
                else:
                    logger.error("发起通话时发生错误：找不到通话按钮")
                    return None, False
                
            except Exception as e:
                logger.error(f"发起通话时发生错误: {e}")
                return None, False

    except Exception as e:
        logger.error(f"发起通话时发生错误: {e}")
        return None, False

# --- 挂断语音通话 ---
def CancelCall(hWnd: int) -> bool:
    """
    取消/终止语音通话。

    Args:
        hWnd: 通话窗口的句柄号。

    Returns:
        若取消/终止成功，返回 True。
        否则返回 False。
    """
    logger.info("尝试挂断语音通话")

    hWnd = hWnd
    if hWnd:
        try:
            call_window = ControlFromHandle(hWnd)
        except Exception as e:
            logger.error(f"取得窗口控制时发生错误: {e}")
            return False
    else:
        logger.error("找不到通话句柄")
        return False

    try:
        hang_up_button = None
        hang_up_button = call_window.ButtonControl(Name=HANG_UP_BUTTON_NAME)
        if hang_up_button.Exists(1):
            '''
            这部分窗口置顶实现参照 wxauto 中的 _show() 方法
            '''
            win32gui.ShowWindow(hWnd, 1)
            win32gui.SetWindowPos(hWnd, -1, 0, 0, 0, 0, 3)
            win32gui.SetWindowPos(hWnd, -2, 0, 0, 0, 0, 3)
            call_window.SwitchToThisWindow()
            hang_up_button.Click()
            logger.info("语音通话已挂断")
            return True
        else:
            logger.error("挂断通话时发生错误：找不到挂断按钮")
            return False

    except Exception as e:
        logger.error(f"挂断通话时发生错误: {e}")
        return False

def PlayVoice(audio_file_path: str, device = None) -> bool:
    """
    播放指定的音频文件到指定的音频输出设备。
    
    Args:
        audio_file_path: 要播放的音频文件路径。
        device: (可选)音频输出设备的名称。
                            默认为 None，此时会使用系统默认输出设备。
    
    Returns:
        若完整播放，返回 True。
        否则返回 False。
    """
    logger.info(f"尝试播放音频文件: '{audio_file_path}'")

    if device:
        logger.info(f"目标输出设备: '{device}'")
    else:
        logger.info("目标输出设备: 系统默认")

    try:
        pygame.mixer.quit()
        pygame.mixer.init(devicename=device)
        pygame.mixer.music.load(audio_file_path)
        time.sleep(2)
        pygame.mixer.music.play()
        logger.info("开始播放音频...")

        # 等待音频播放完毕
        # 注意：如果 PlayVoice 需要在后台播放而不阻塞主线程，
        # 这部分等待逻辑需要移除或修改。
        # 当前实现是阻塞的，直到播放完成。
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        
        logger.info("音频播放完毕。")
        return True

    except pygame.error as e:
        logger.error(f"Pygame 错误:{e}")
        return False
    except FileNotFoundError:
        logger.error(f"音频文件未找到:'{audio_file_path}'")
        return False
    except Exception as e:
        logger.error(f"发生未知错误:{e}")
        return False
    finally:
        if pygame.mixer.get_init(): # 检查 mixer 是否已初始化
            pygame.mixer.music.stop()
            pygame.mixer.quit()



def Call(wx: WeChat, who: str, audio_file_path: str) -> None:
    """
    尝试向指定对象发起语音通话，接通后会将指定音频文件输入麦克风，并自动挂断。

    Args:
        wx: 微信实例。
        who: 通话对象。
        audio_file_path: 音频文件路径。
    
    Returns:
        None
    """
    call_hwnd, success = CallforWho(wx, who)
    if not success:
        logger.error(f"发起通话失败")
        return
    logger.info(f"等待对方接听 (等待{CALL_TIME_OUT}秒)...")

    start_time = time.time()
    call_status = 0
    call_window = None

    try:
        call_window = ControlFromHandle(call_hwnd)
        # --- 判断通话状态 ---
        while time.time() - start_time < CALL_TIME_OUT:
            '''
            后续会补充通话状态判别原理。
            '''

            # if not call_window.Exists(0.2, 0.1): # 检查窗口是否在轮询期间关闭
            #     logger.warning(f"通话窗口 (句柄: {call_hwnd}) 在等待接听时关闭或不再有效 (可能对方已拒接或发生错误)。")
            #     call_answered = False # 确保状态
            #     break 

            hang_up_text = call_window.TextControl(Name=HANG_UP_BUTTON_LABEL)
            refuse_msg = call_window.TextControl(Name=REFUSE_MSG)
            if hang_up_text.Exists(0.1, 0.1) and not refuse_msg.Exists(0.1, 0.1):
                logger.info(f"通话已接通！")
                call_status = 1
                break
            elif hang_up_text.Exists(0.1, 0.1) and refuse_msg.Exists(0.1, 0.1):
                logger.info(f"通话被拒接！")
                call_status = 2
                break
            else:
                continue

        # --- 根据通话状态执行相应操作 ---
        if call_status == 1:
            '''
            待完成：
            1. 接通后如何捕捉挂断行为？
            2. 挂断后如何中断语音播放？
            3. bot 是否要针对挂断做出个性化回应？
            '''
            PlayVoice(audio_file_path=audio_file_path)
            logger.info("语音播放完成，即将挂断...")
            CancelCall(call_hwnd)
        elif call_status ==2:
            '''
            待完成：
            1. 可以让 bot 回复信息对拒接表示生气。
            '''
            pass
        else:
            '''
            待完成：
            1. 可以让 bot 回复信息对未接听表示生气。
            '''
            logger.info(f"在超时时间内，对方未接听通话。")
            CancelCall(call_hwnd)

    except Exception as e:
        logger.error(f"处理通话时发生未知错误: {e}")
        if call_hwnd is not None: # 对错误进行简单处理，确保有句柄再尝试取消
            CancelCall(call_hwnd)

# --- 主程序示例 (仅用于测试版) ---
if __name__ == '__main__':
    # 配置日志记录
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s: %(message)s',
        handlers=[
            logging.StreamHandler() # 输出到控制台
        ]
    )
    logger.info("程序启动")
    wx = WeChat()
    who = "" # 输入通话对象名称
    if wx and who:
        try:
            Call(wx, who, 'test.mp3')
        except Exception as main_e:
            logger.error(f"主程序执行过程中发生错误: {main_e}", exc_info=True)
    else:
        logger.error("未能初始化 WeChat 对象或未指定通话对象。")

    logger.info("程序结束")
from je_auto_control.windows.window.window_hwnd import get_all_window_hwnd, post_message_to_window, messages

hwnd_list = get_all_window_hwnd()
print(hwnd_list)

for hwnd, name in hwnd_list:
    print(hwnd, name)
    if name == "Messenger":
        print(post_message_to_window("Messenger", messages.get("WM_CLOSE"), 0, 0))
        break

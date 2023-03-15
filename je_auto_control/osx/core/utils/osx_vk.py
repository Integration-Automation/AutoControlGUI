import sys

from je_auto_control.utils.exception.exception_tags import osx_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error)

# osx keyboard virtual keycode

osx_key_a = osx_key_A = 0x00
osx_key_s = osx_key_S = 0x01
osx_key_d = osx_key_D = 0x02
osx_key_f = osx_key_F = 0x03
osx_key_h = osx_key_H = 0x04
osx_key_g = osx_key_G = 0x05
osx_key_z = osx_key_Z = 0x06
osx_key_x = osx_key_X = 0x07
osx_key_c = osx_key_C = 0x08
osx_key_v = osx_key_V = 0x09
osx_key_b = osx_key_B = 0x0b
osx_key_q = osx_key_Q = 0x0c
osx_key_w = osx_key_W = 0x0d
osx_key_e = osx_key_E = 0x0e
osx_key_r = osx_key_R = 0x0f
osx_key_y = osx_key_Y = 0x10
osx_key_t = osx_key_T = 0x11
osx_key_1 = osx_key_exclam = 0x12
osx_key_2 = osx_key_at = 0x13
osx_key_3 = osx_key_numbersign = 0x14
osx_key_4 = osx_key_money = 0x15
osx_key_6 = osx_key_asciicircum = 0x16
osx_key_5 = osx_key_percent = 0x17
osx_key_equal = osx_key_plus = 0x18
osx_key_9 = osx_key_parenleft = 0x19
osx_key_7 = osx_key_ampersand = 0x1a
osx_key_minus = osx_key_underscore = 0x1b
osx_key_8 = osx_key_asterisk = 0x1c
osx_key_0 = osx_key_parenright = 0x1d
osx_key_bracketright = osx_key_braceright = 0x1e
osx_key_o = osx_key_O = 0x1f
osx_key_u = osx_key_U = 0x20
osx_key_bracketleft = osx_key_braceleft = 0x21
osx_key_i = osx_key_I = 0x22
osx_key_p = osx_key_P = 0x23
osx_key_l = osx_key_L = 0x25
osx_key_j = osx_key_J = 0x26
osx_key_apostrophe = osx_key_quotedbl = 0x27
osx_key_k = osx_key_K = 0x28
osx_key_semicolon = osx_key_colon = 0x29
osx_key_backslash = osx_key_bar = 0x2a
osx_key_comma = osx_key_less = 0x2b
osx_key_salsh = osx_key_question = 0x2c
osx_key_n = osx_key_N = 0x2d
osx_key_m = osx_key_M = 0x2e
osx_key_period = osx_key_greater = 0x2f
osx_key_grave = osx_key_asciitilde = 0x32
osx_key_space = 0x31
osx_key_return = osx_key_newline = osx_key_enter = 0x24
osx_key_tab = 0x30
osx_key_backspace = 0x33
osx_key_esc = 0x35
osx_key_command = 0x37
osx_key_shift = 0x38
osx_key_caps_lock = 0x39
osx_key_option = osx_key_alt = 0x3a
osx_key_ctrl = 0x3b
osx_key_shift_right = 0x3c
osx_key_option_right = 0x3d
osx_key_control_right = 0x3e
osx_key_fn = 0x3f
osx_key_f17 = 0x40
osx_key_volume_up = 0x48
osx_key_volume_down = 0x49
osx_key_volume_mute = 0x4a
osx_key_f18 = 0x4f
osx_key_f19 = 0x50
osx_key_f20 = 0x5a
osx_key_f5 = 0x60
osx_key_f6 = 0x61
osx_key_f7 = 0x62
osx_key_f3 = 0x63
osx_key_f8 = 0x64
osx_key_f9 = 0x65
osx_key_f11 = 0x67
osx_key_f13 = 0x69
osx_key_f16 = 0x6a
osx_key_f14 = 0x6b
osx_key_f10 = 0x6d
osx_key_f12 = 0x6f
osx_key_f15 = 0x71
osx_key_help = 0x72
osx_key_home = 0x73
osx_key_pageup = 0x74
osx_key_delete = 0x75
osx_key_f4 = 0x76
osx_key_end = 0x77
osx_key_f2 = 0x78
osx_key_pagedown = 0x79
osx_key_f1 = 0x7a
osx_key_left = 0x7b
osx_key_right = 0x7c
osx_key_down = 0x7d
osx_key_up = 0x7e
osx_key_yen = 0x5d
osx_key_eisu = 0x66
osx_key_kana = 0x68
"""
osx mouse virtual keycode
"""
osx_mouse_left = "Left"
osx_mouse_middle = "Middle"
osx_mouse_right = "Right"

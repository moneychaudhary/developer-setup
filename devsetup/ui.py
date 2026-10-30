import os
import sys


def key_decision(key):
    if key in ('\r', '\n'):
        return True
    if key in ('\x7f', '\x08', '\x1b[3~'):
        return False
    if key == '\x03':
        raise KeyboardInterrupt
    return None


def ask(message):
    if not sys.stdin.isatty():
        raise RuntimeError('Interactive input required; use --yes with an explicit selection.')
    print(f'{message} [Enter] Yes · [Delete/Backspace] Skip', flush=True)
    if os.name == 'nt':
        import msvcrt
        while True:
            key = msvcrt.getwch()
            if key in ('\x00', '\xe0'):
                key = '\x7f' if msvcrt.getwch() == 'S' else ''
            result = key_decision(key)
            if result is not None:
                print('Yes' if result else 'Skipped')
                return result
    import termios
    import tty
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            key = os.read(fd, 1).decode()
            if key == '\x1b':
                import select
                for _ in range(3):
                    if not select.select([fd], [], [], 0.1)[0]:
                        break
                    key += os.read(fd, 1).decode()
            result = key_decision(key)
            if result is not None:
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
    print('Yes' if result else 'Skipped')
    return result

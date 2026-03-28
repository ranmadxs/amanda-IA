#!/usr/bin/env python3
"""
Test: ¿llegan eventos de mouse al servidor via SSH?
Correr: python3 scripts/test_mouse_ssh.py
Después clickear con el mouse. Ctrl+C para salir.
"""
import sys
import os
import tty
import termios

def main():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        # Habilitar mouse reporting SGR
        sys.stdout.write("\x1b[?1000h\x1b[?1006h")
        sys.stdout.flush()
        sys.stdout.write("Clickeá con el mouse (Ctrl+C para salir):\r\n")
        sys.stdout.flush()

        while True:
            ch = sys.stdin.read(1)
            if ch == "\x03":  # Ctrl+C
                break
            data = bytearray()
            data.extend(ch.encode())
            # Leer más bytes si hay secuencia de escape
            if ch == "\x1b":
                sys.stdin
                import select
                while select.select([sys.stdin], [], [], 0.05)[0]:
                    c = sys.stdin.read(1)
                    data.extend(c.encode())
                    if c.isalpha() or c == "~":
                        break
            sys.stdout.write(f"bytes: {list(data)} repr: {repr(bytes(data))}\r\n")
            sys.stdout.flush()
    finally:
        # Deshabilitar mouse
        sys.stdout.write("\x1b[?1000l\x1b[?1006l")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

if __name__ == "__main__":
    main()

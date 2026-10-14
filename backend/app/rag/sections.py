"""Canonical appendix labels retain heading context across page boundaries."""
import re
import unicodedata


def section_key(text: str) -> str:
    value = ''.join(char for char in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(char))
    match = re.match(r'\s*(phu luc|appendix)\s+(\d+|[ivxlcdm]+)\b', value)
    if not match:
        return ' '.join(value.split())
    token = match[2]
    if token.isdigit():
        number = int(token)
    else:
        roman = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}
        number, previous = 0, 0
        for char in reversed(token):
            current = roman[char]
            number += -current if current < previous else current
            previous = max(previous, current)
    return f'appendix:{number}'

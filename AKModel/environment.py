"""
Environment definitions
Needed for tex compilation
"""
import re

from django_tex.environment import environment

# Used to filter all very special UTF-8 chars that are probably not contained in the LaTeX fonts
# and would hence cause compilation errors
utf8_replace_pattern = re.compile('[^\u0000-\u206F]', re.UNICODE)


def latex_escape_utf8(value):
    """
    Escape latex special chars and remove invalid utf-8 values

    :param value: string to escape
    :type value: str
    :return: escaped string
    :rtype: str
    """
    return (utf8_replace_pattern.sub('', value).replace('&', r'\&').replace('_', r'\_').replace('#', r'\#').
            replace('$', r'\$').replace('%', r'\%').replace('{', r'\{').replace('}', r'\}'))


def improved_tex_environment(**options):
    """
    Encapsulate our improved latex environment for usage
    """
    env = environment(**options)
    env.filters.update({
        'latex_escape_utf8': latex_escape_utf8,
    })
    return env

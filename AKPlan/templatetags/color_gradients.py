# gradients based on http://bsou.io/posts/color-gradients-with-python


def hex_to_rgb(hex): #pylint: disable=redefined-builtin
    """
    Convert hex color to RGB color code
    :param hex: hex encoded color
    :type hex: str
    :return: rgb encoded version of given color
    :rtype: list[int]
    """
    # Pass 16 to the integer function for change of base
    return [int(hex[i:i+2], 16) for i in range(1,6,2)]


def rgb_to_hex(rgb):
    """
    Convert rgb color (list) to hex encoding (str)
    :param rgb: rgb encoded color
    :type rgb: list[int]
    :return: hex encoded version of given color
    :rtype: str
    """
    # Components need to be integers for hex to make sense
    rgb = [int(x) for x in rgb]
    return "#"+"".join([f"0{v:x}" if v < 16 else f"{v:x}" for v in rgb])


def linear_blend(start_hex, end_hex, position):
    """
    Create a linear blend between two colors and return color code on given position of the range from 0 to 1
    :param start_hex: hex representation of start color
    :type start_hex: str
    :param end_hex: hex representation of end color
    :type end_hex: str
    :param position: position in range from 0 to 1
    :type position: float
    :return: hex encoded interpolated color
    :rtype: str
    """
    s = hex_to_rgb(start_hex)
    f = hex_to_rgb(end_hex)
    blended = [int(s[j] + position * (f[j] - s[j])) for j in range(3)]
    return rgb_to_hex(blended)


def darken(start_hex, amount):
    """
    Darken the given color by the given amount (sensitivity will be cut in half)

    :param start_hex: original color
    :type start_hex: str
    :param amount: how much to darken (1.0 -> 50% darker)
    :type amount: float
    :return: darker version of color
    :rtype: str
    """
    start_rbg = hex_to_rgb(start_hex)
    darker = [int(s * (1 - amount * .5)) for s in start_rbg]
    return rgb_to_hex(darker)

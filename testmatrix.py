from threading import Event

from board import NCAAHockeyTicker


class FakeMatrix:
    def clear(self):
        print("clear")

    def draw_text(self, position, text, font=None, fill=None, align=None):
        print(f"draw_text: pos={position}, text={text}, fill={fill}, align={align}")

    def draw_text_layout(self, layout, text, fillColor=None):
        print(f"draw_text_layout: layout={layout}, text={text}, fill={fillColor}")

    def draw_image(self, position, image):
        print(f"draw_image: pos={position}, size={image.size}")

    def render(self):
        print("render")


class FakeLayout:
    font_small = "small"
    font = "medium"
    font_large = "large"


class FakeConfig:
    layout = FakeLayout()


class FakeData:
    config = FakeConfig()


board = NCAAHockeyTicker(FakeData(), FakeMatrix(), Event())
board.render()
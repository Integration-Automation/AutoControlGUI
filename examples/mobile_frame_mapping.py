"""Map Retina/display-rotated PNG coordinates without connecting or sending input."""
import io

from PIL import Image

from je_auto_control.api.mobile import DeviceContext, DeviceFrame, Gesture


def main() -> None:
    """Build immutable device evidence and prepare an unsent native-point gesture."""
    output = io.BytesIO()
    with Image.new('RGB', (600, 300), 'navy') as image:
        image.save(output, format='PNG')
    frame = DeviceFrame(output.getvalue(), DeviceContext('ios', 'example', target='http://127.0.0.1:8100'),
                        (300, 150), orientation=90)
    point = frame.pixel_to_point((200, 100))
    rotated_point = frame.rotated(90).pixel_to_point((199, 200))
    assert point == rotated_point == (100, 50)
    gesture = Gesture('tap', (point,))
    print(f'Prepared only: {gesture}; no device connection or input')


if __name__ == '__main__':
    main()

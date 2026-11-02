import unittest
from binascii import a2b_hex
from custom_components.artnet_led.client.sacn_server import SacnServer, SacnPacket


class TestSacnServer(unittest.TestCase):
    def test_deserialization(self):
        hex_data = (
            '001000004153432d45312e31370000007078000000044168f52b1a7b2de11712e9ee383d225870620000000264656661756c7420'
            '736f75726365206e616d650000000000000000000000000000000000000000000000000000000000000000000000000000000000'
            '0000000064000000000001701502a100000001000b000102030405060708090a'
        )
        packet = SacnPacket.deserialize(a2b_hex(hex_data))
        self.assertIsNotNone(packet)
        self.assertEqual(packet.universe, 1)
        self.assertEqual(packet.priority, 100)
        self.assertEqual(packet.source_name, 'default source name')
        self.assertEqual(list(packet.dmx_data), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

    def test_multicast_ip_calculation(self):
        self.assertEqual(SacnServer.get_multicast_ip(1), '239.255.0.1')
        self.assertEqual(SacnServer.get_multicast_ip(256), '239.255.1.0')


if __name__ == '__main__':
    unittest.main()

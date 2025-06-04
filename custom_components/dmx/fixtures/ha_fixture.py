# https://raw.githubusercontent.com/OpenLightingProject/open-fixture-library/master/schemas/fixture.json
import json
import logging

from homeassistant.exceptions import IntegrationError
from homeassistant.helpers.entity import DeviceInfo

from custom_components.dmx.fixtures.model import HaFixture

log = logging.getLogger(__name__)


class UnknownModeError(IntegrationError):
    def __init__(self, fixture: str, mode: str, *args: object) -> None:
        super().__init__(*args)
        self._fixture = fixture
        self._mode = mode

    def __str__(self) -> str:
        return f"Mode '{self._mode}' does not exist in fixture '{self._fixture}'"


class NotImplementedYet(IntegrationError):
    def __init__(self, feature: str, *args: object) -> None:
        super().__init__(*args)
        self._feature = feature

    def __str__(self) -> str:
        return f"The feature {self._feature} isn't implemented yet." \
               f"Consider creating a GitHub issue if this is what you need."


def parse_json(filename: str) -> HaFixture:
    with open(filename) as user_file:
        fixture_json = json.load(user_file)

        name = fixture_json['name']
        short_name = fixture_json.get('shortName', name)

        meta = fixture_json['meta']

        links = meta.get('links', {})
        links_manual = links.get('manual')
        links_product_page = links.get('productPage')
        links_video = links.get('video')
        links_other = links.get('other')

        help_wanted = fixture_json.get('helpWanted')

        fixture_key = fixture_json['fixtureKey']
        manufacturer_key = fixture_json['manufacturerKey']
        of_url = fixture_json['oflURL']

        rdm = fixture_json.get('rdm', {})
        rdm_model_id = rdm.get('modelId')
        rdm_software_version = rdm.get('softwareVersion')

        referenced_name = fixture_key or short_name or name
        device_info = DeviceInfo(
            configuration_url=(of_url or links_manual or links_product_page or links_video or links_other),
            manufacturer=manufacturer_key,
            model=(rdm_model_id or fixture_key),
            sw_version=rdm_software_version,
            name=name
        )

        if help_wanted:
            log.info(f"Looks like {name}'s fixture JSON could use some love, please head over to {of_url}")

        return HaFixture(referenced_name, device_info, fixture_json)


# def implement(fixture: HaFixture, device_name: str, port_address: PortAddress, universe: BaseUniverse, start_channel: int,
#               target_mode: Union[str, None]):
#     fixture_json = fixture.fixture_json
#
#     channels = get_channels_for_mode(fixture_json, target_mode)
#     available_channels = fixture_json.get('availableChannels')
#
#     if not available_channels:
#         raise NotImplementedYet('templateChannels')
#
#     channel_number = start_channel
#     entities: array[BaseEntity] = []
#
#     for channel_name in channels:
#         channel = available_channels[channel_name]
#
#         capability = channel.get('capability')  # TODO capabilities
#         if capability:
#             capability_type = capability['type']
#             if capability_type == 'Intensity':
#                 dmx_channel = universe.add_channel(
#                     start=channel_number,
#                     width=1,
#                     channel_name=channel_name,
#                     byte_size=1,
#                     byte_order='big',
#                 )
#                 entities.append(
#                     IntensityNumber(fixture, device_name, channel_name, port_address, dmx_channel)
#                 )
#
#         channel_number += 1
#
#     return entities


def get_channels_for_mode(fixture: dict, target_mode: str):
    modes = fixture['modes']
    if target_mode is None:
        if len(modes) == 1:
            return modes[0]['channels']
        else:
            raise UnknownModeError(fixture['name'], 'None')

    for mode in modes:
        name = mode.get('shortName', mode['name'])
        if name == target_mode:
            return mode['channels']

    raise UnknownModeError(fixture['name'], target_mode)

    # name = raw['name']
    # name = raw.get('shortName', name)
    # categories = raw['categories']
    #
    # meta = raw['meta']
    # authors = meta['authors']
    # create_date = meta['createDate']
    # modify_date = meta['lastModifyDate']
    #
    # comment = meta.get('comment')
    #
    # links = meta.get('links', {})
    # links_manual = links.get('manual')
    # links_product_page = links.get('productPage')
    # links_video = links.get('video')
    # links_other = links.get('other')
    #
    # help_wanted = raw.get('helpWanted')
    #
    # rdm = raw.get('rdm', {})
    # rdm_model_id = rdm.get('modelId')
    # rdm_software_version = rdm.get('softwareVersion')
    #
    # physical = raw.get('physical', {})
    # physical_dimensions = physical.get('dimensions')
    # physical_weight = physical.get('weight')
    # physical_power = physical.get('power')
    # physical_dmx_connector = physical.get('DMXconnector')
    #
    # physical_bulb = physical.get('bulb', {})
    # physical_bulb_type = physical_bulb.get('type')
    # physical_bulb_color_temperature = physical_bulb.get('colorTemperature')
    # physical_bulb_lumens = physical_bulb.get('lumens')
    #
    # physical_lens = physical.get('lens', {})
    # physical_lens_name = physical_lens.get('name')
    # physical_lens_degreesMinMax = physical_lens.get('degreesMinMax')
    #
    # physical_matrixPixels = physical.get('matrixPixels', {})
    # physical_matrixPixels_dimensions = physical_matrixPixels.get('dimensions')
    # physical_matrixPixels_spacing = physical_matrixPixels.get('spacing')
    #
    # matrix = raw.get('matrix') # TODO
    #
    # wheels = raw.get('wheels', {})

# jsonny = parse_json("F:/Projects/Home/ha-artnet-led/staging/fixtures/hotbox-rgbw.json")
#
# implement(jsonny, 1, '9bCh')

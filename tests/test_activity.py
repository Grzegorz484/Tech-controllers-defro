import pytest

from custom_components.defro_emodul.activity import tile_activity


def activity(catalogue, snapshot, key, *, last_update_success=True):
    spec = next(s for s in catalogue['entities'] if s['key'] == key)
    return tile_activity(spec, snapshot, last_update_success=last_update_success)


@pytest.mark.parametrize('key,animation,active', [
    ('tile_1002_workingstatus', 'feed', False),
    ('tile_1003_workingstatus', 'heat', False),
    ('tile_1004_workingstatus', 'pump', True),
    ('tile_1005_workingstatus', 'pump', False),
    ('tile_1011_gear', 'fan', True),
    ('tile_1011_workingstatus', 'fan', True),
    ('tile_1012_openingpercentage', 'valve', True),
    ('tile_1012_workingstatus', 'valve', True),
    ('tile_1012_valvepump', 'pump', True),
])
def test_known_device_fields_have_animation_metadata(catalogue, snapshot, key, animation, active):
    result = activity(catalogue, snapshot, key)
    assert result['animation'] == animation
    assert result['active'] is active


@pytest.mark.parametrize('raw,active', [
    (True, True), (False, False), (1, True), (0, False),
    ('true', True), ('false', False), ('t', True), ('f', False),
    ('on', True), ('off', False), ('TRUE', True),
    (None, False), ('1', False), ('0', False), ('unknown', False),
    (2, False), (1.0, False),
])
def test_activity_uses_validated_boolean_states(catalogue, snapshot, raw, active):
    snapshot['sections']['tile']['elements'][1004]['params']['workingStatus'] = raw
    result = activity(catalogue, snapshot, 'tile_1004_workingstatus')
    assert result['animation'] == 'pump'
    assert result['active'] is active


@pytest.mark.parametrize('key,element_id,field', [
    ('tile_1011_gear', 1011, 'workingStatus'),
    ('tile_1012_openingpercentage', 1012, 'workingStatus'),
    ('tile_1012_valvepump', 1012, 'valvePump'),
])
def test_numeric_readings_and_other_flags_do_not_imply_device_activity(
    catalogue, snapshot, key, element_id, field
):
    params = snapshot['sections']['tile']['elements'][element_id]['params']
    params[field] = False
    assert not activity(catalogue, snapshot, key)['active']
    params.pop(field)
    assert not activity(catalogue, snapshot, key)['active']


def test_valve_pump_has_its_own_state_and_pump_icon(catalogue, snapshot):
    params = snapshot['sections']['tile']['elements'][1012]['params']
    params['workingStatus'] = False
    result = activity(catalogue, snapshot, 'tile_1012_valvepump')
    assert result == {'icon': 'mdi:pump', 'animation': 'pump', 'active': True}
    assert not activity(catalogue, snapshot, 'tile_1012_openingpercentage')['active']
    params['workingStatus'] = True
    params['valvePump'] = False
    assert not activity(catalogue, snapshot, 'tile_1012_valvepump')['active']
    assert activity(catalogue, snapshot, 'tile_1012_openingpercentage')['active']


@pytest.mark.parametrize('key', [
    'tile_1006_value', 'tile_1006_workingstatus',
    'tile_1008_workingstatus', 'tile_1010_percentage',
    'tile_1012_currenttemp', 'tile_1012_returntemp', 'tile_1012_settemp',
    'tile_1012_boilerprotection', 'tile_1012_returnprotection',
    'tile_1016_workingstatus', 'tile_1016_value', 'tile_2040_statusid',
    'mu_2060_value',
])
def test_measurements_diagnostics_protection_and_menu_settings_stay_static(catalogue, snapshot, key):
    result = activity(catalogue, snapshot, key)
    assert result['animation'] == ''
    assert result['active'] is False


@pytest.mark.parametrize('failure', [
    'controller_offline', 'cloud_failure', 'section_error', 'hidden',
    'updating', 'schema_changed', 'element_missing', 'parameters_missing',
])
def test_unavailable_device_readings_never_animate(catalogue, snapshot, failure):
    section = snapshot['sections']['tile']
    item = section['elements'][1004]
    if failure == 'controller_offline':
        snapshot['online'] = False
    elif failure == 'section_error':
        section['status'] = 'error'
    elif failure == 'hidden':
        item['visibility'] = False
    elif failure == 'updating':
        item['duringChange'] = 't'
    elif failure == 'schema_changed':
        item['type'] = 99
    elif failure == 'element_missing':
        section['elements'].pop(1004)
    elif failure == 'parameters_missing':
        item.pop('params')
    result = activity(catalogue, snapshot, 'tile_1004_workingstatus',
                      last_update_success=failure != 'cloud_failure')
    assert result['animation'] == 'pump'
    assert result['active'] is False


@pytest.mark.parametrize('raw', [None, False, 'unknown'])
def test_fan_requires_its_own_reading_as_well_as_a_working_flag(catalogue, snapshot, raw):
    snapshot['sections']['tile']['elements'][1011]['params']['gear'] = raw
    assert activity(catalogue, snapshot, 'tile_1011_gear')['active'] is False
    assert activity(catalogue, snapshot, 'tile_1011_workingstatus')['active'] is True


def test_missing_snapshot_and_diagnostic_device_flags_stay_inactive(catalogue, snapshot):
    spec = next(s for s in catalogue['entities'] if s['key'] == 'tile_1004_workingstatus')
    assert not tile_activity(spec, None, last_update_success=True)['active']
    result = tile_activity({**spec, 'diagnostic': True}, snapshot, last_update_success=True)
    assert result['animation'] == ''
    assert result['active'] is False

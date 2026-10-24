import math

import pytest

from custom_components.defro_emodul.model import read_entity


def spec(catalogue,key):
    return next(s for s in catalogue['entities'] if s['key']==key)


def test_full_catalogue_is_317_live_definitions(catalogue,snapshot):
    specs=catalogue['entities']
    assert len(specs)==317
    assert sum(x['platform']=='sensor' for x in specs)==261
    assert sum(x['platform']=='binary_sensor' for x in specs)==56
    assert len({x['key'] for x in specs})==317
    assert all('raw_value' not in x and 'native_value_snapshot' not in x for x in specs)
    assert {x['element_id'] for x in specs if x['section']=='MU'}=={
        e['id'] for e in snapshot['sections']['MU']['elements'].values() if e.get('type') in (1,2,3,4,10,11,12,13,15,30)
    }


@pytest.mark.parametrize('key,value',[
    ('tile_1006_value',60.5),('tile_1008_value',100),('tile_1009_value',11),
    ('tile_1017_value',20.5),('tile_1012_currenttemp',45.5),('tile_1012_returntemp',40),
    ('tile_1012_settemp',45),('mu_2060_value',60),('mu_2061_value',45),
    ('mu_2089_value',21.5),('tile_1004_workingstatus',True),('tile_1005_workingstatus',False),
    ('tile_1001_statusid','Ogrzewanie domu'),('tile_2040_statusid','Praca PID'),
])
def test_synthetic_payload_decoding(catalogue,snapshot,key,value):
    reading=read_entity(spec(catalogue,key),snapshot)
    assert reading.available
    assert reading.value==value


def test_values_are_live_not_from_seed(catalogue,snapshot):
    snapshot['sections']['tile']['elements'][1006]['params']['value']=715
    snapshot['sections']['tile']['elements'][1004]['params']['workingStatus']=False
    assert read_entity(spec(catalogue,'tile_1006_value'),snapshot).value==71.5
    assert read_entity(spec(catalogue,'tile_1004_workingstatus'),snapshot).value is False


@pytest.mark.parametrize('raw,available,expected',[(0,True,0),(None,False,None),(False,False,None),('not a number',False,None),(math.inf,False,None)])
def test_zero_missing_and_invalid_values_are_distinct(catalogue,snapshot,raw,available,expected):
    snapshot['sections']['tile']['elements'][1006]['params']['value']=raw
    r=read_entity(spec(catalogue,'tile_1006_value'),snapshot)
    assert r.available is available
    assert r.value==expected


def test_offline_or_failed_sections_do_not_show_previous_values(catalogue,snapshot):
    snapshot['online']=False
    assert not read_entity(spec(catalogue,'tile_1006_value'),snapshot).available
    snapshot['online']=True
    snapshot['sections']['tile']['status']='error'
    r=read_entity(spec(catalogue,'tile_1006_value'),snapshot)
    assert not r.available and r.value is None


def test_access_flags_and_schema_changes(catalogue,snapshot):
    r=read_entity(spec(catalogue,'mi_4746_value'),snapshot)
    assert not r.available and r.reason=='api_access_false'
    snapshot['sections']['tile']['elements'][1006]['type']=99
    assert read_entity(spec(catalogue,'tile_1006_value'),snapshot).reason=='schema_changed'
    snapshot['sections']['tile']['elements'][1006]['type']=1
    snapshot['sections']['tile']['elements'][1006]['visibility']=False
    assert not read_entity(spec(catalogue,'tile_1006_value'),snapshot).available


def test_pending_change_does_not_publish_old_setting(catalogue,snapshot):
    snapshot['sections']['MU']['elements'][2060]['duringChange']='t'
    r=read_entity(spec(catalogue,'mu_2060_value'),snapshot)
    assert not r.available and r.reason=='value_updating'


def test_curve_points_match_positions_not_array_order(catalogue,snapshot):
    item=snapshot['sections']['MI']['elements'][2217]
    item['params']['points']=list(reversed(item['params']['points']))
    r=read_entity(spec(catalogue,'mi_2217_point_m20'),snapshot)
    assert r.value==60


def test_midnight_and_empty_schedule_are_valid_zero(catalogue,snapshot):
    snapshot['sections']['MS']['elements'][3765]['params']['value']=0
    assert read_entity(spec(catalogue,'ms_3765_value'),snapshot).value=='00:00'
    r=read_entity(spec(catalogue,'mu_3201_values_count'),snapshot)
    assert r.available and r.value==0 and r.attributes['values']==[]


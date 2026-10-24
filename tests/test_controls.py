"""Protocol conversions, live permissions and validation without a real boiler."""
import copy

import pytest

from custom_components.defro_emodul.controls import describe_controls, prepare_write


def menu(kind, params, **overrides):
    item = {'id':10,'parentId':0,'type':kind,'access':True,'txtId':10,'params':params,**overrides}
    return {'online':True,'texts':{'10':'Temperatura CO','11':'Włączone','12':'Wyłączone'},
            'sections':{'MU':{'status':'ok','elements':{
                0:{'id':0,'parentId':0,'type':0,'access':True,'params':{}},10:item}}}}


def control(kind, params, **overrides):
    return next(i for i in describe_controls(menu(kind, params, **overrides),virtual=True) if i['key']=='mu_10')


@pytest.mark.parametrize('kind,params,value,expected',[
    (1,{'min':40,'max':80,'value':70},71,{'value':71}),
    (2,{'min':50,'max':400,'value':220},21.7,{'value':217}),
    (1,{'format':2,'min':50,'max':400,'value':220},21.7,{'value':217}),
    (3,{'min':1,'max':120,'value':60},90,{'value':90}),
    (4,{'min':0,'max':3600,'value':2400},3600,{'value':3600}),
    (10,{'value':0},True,{'value':1}),
    (11,{'value':3,'options':[{'txtId':11,'value':3},{'txtId':12,'value':9}]},'Wyłączone',{'value':9}),
    (15,{'value':0,'options':[11,12]},[1,0],{'many_of_many':[{'id':0,'value':1},{'id':1,'value':0}]}),
    (30,{'min':20,'max':70,'points':[{'position':-20,'value':60},{'position':10,'value':30}]},[65,35],{'heating_curve':[{'id':0,'value':65},{'id':1,'value':35}]}),
    (12,{'min':-25,'max':25,'values':[]},[-2]*24,{'weekly_plus_minus':{'values':[23]*24}}),
    (13,{'noZones':48,'value':2**47},[0]*47+[1],{'weekly_on_off':{'values':[0]*47+[1]}}),
])
def test_documented_wire_format(kind,params,value,expected):
    payload,_=prepare_write(control(kind,params),value)
    assert payload==expected


@pytest.mark.parametrize('kind,params,value',[
    (1,{'min':40,'max':80,'value':70},81),
    (1,{'min':0,'max':10,'jump':2,'value':0},3),
    (2,{'min':50,'max':400,'value':220},21.75),
    (1,{'min':0,'max':10,'value':0},True),
    (1,{'min':0,'max':10,'value':0},float('nan')),
    (10,{'value':0},1),
    (11,{'value':3,'options':[{'txtId':11,'value':3}]},'missing'),
    (15,{'value':0,'options':[11,12]},[1]),
    (30,{'min':20,'max':70,'points':[{'position':-20,'value':60}]},[71]),
    (12,{'min':-25,'max':25,'values':[]},[0]*23),
    (12,{'min':-25,'max':25,'values':[]},[26]*24),
    (13,{'noZones':24,'value':0},[2]*24),
])
def test_invalid_values_are_rejected(kind,params,value):
    with pytest.raises(ValueError):prepare_write(control(kind,params),value)


@pytest.mark.parametrize('change', ['offline','own_access','parent_access','missing_parent','parent_locked','changing','parent_changing','no_bounds'])
def test_writes_require_current_permission_and_metadata(change):
    data=menu(1,{'min':40,'max':80,'value':70})
    root=data['sections']['MU']['elements'][0];item=data['sections']['MU']['elements'][10]
    if change=='offline':data['online']=False
    if change=='own_access':item['access']=False
    if change=='parent_access':root['access']=False
    if change=='missing_parent':item['parentId']=99
    if change=='parent_locked':root['params']={'password':'password'}
    if change=='changing':item['duringChange']='t'
    if change=='parent_changing':root['duringChange']='t'
    if change=='no_bounds':del item['params']['min']
    info=next(i for i in describe_controls(data) if i['key']=='mu_10')
    assert not info['available']
    with pytest.raises(ValueError):prepare_write(info,71)


def test_virtual_checkbox_and_curve_preserve_other_values():
    data=menu(15,{'value':2,'options':[11,12]})
    info=next(i for i in describe_controls(data,virtual=True) if i['key']=='mu_10_option_0')
    assert prepare_write(info,True)==({'many_of_many':[{'id':0,'value':1},{'id':1,'value':1}]},{'value':3})
    data=menu(30,{'min':20,'max':70,'points':[{'position':-20,'value':60},{'position':10,'value':30}]})
    info=next(i for i in describe_controls(data,virtual=True) if i['key']=='mu_10_point_-20')
    assert prepare_write(info,65)[0]=={'heating_curve':[{'id':0,'value':65},{'id':1,'value':30}]}


@pytest.mark.parametrize('subtype,answer',[(0,2),(1,1),(2,3)])
def test_actions_need_explicit_confirmation(subtype,answer):
    info=control(20,{'type':subtype,'txtId':10})
    with pytest.raises(ValueError):prepare_write(info,True)
    with pytest.raises(ValueError):prepare_write(info,False,confirm=True)
    assert prepare_write(info,True,confirm=True)==({'value':answer,'type':subtype},{})


def test_descriptions_never_return_passwords_or_mutate_the_snapshot():
    data=menu(35,{'password':['private-menu-code']})
    before=copy.deepcopy(data)
    items=describe_controls(data,virtual=True)
    assert 'private-menu-code' not in str(items)
    assert data==before
    assert next(i for i in items if i['key']=='mu_10')['can_unlock']
    data['sections']['MS']={'status':'locked','elements':{}}
    assert next(i for i in describe_controls(data) if i['key']=='ms_0')['can_unlock']


def test_unknown_types_remain_visible_but_cannot_be_written():
    info=control(999,{'value':1})
    assert info['kind']=='unsupported' and not info['available']
    with pytest.raises(ValueError):prepare_write(info,1)


def test_duplicate_option_names_are_unambiguous():
    info=control(11,{'value':3,'options':[{'txtId':11,'value':3},{'txtId':11,'value':9}]})
    assert [o['label'] for o in info['options']]==['Włączone (3)','Włączone (9)']

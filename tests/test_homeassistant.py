import copy
from unittest.mock import AsyncMock
from time import monotonic
from types import SimpleNamespace

import pytest

from homeassistant.config_entries import ConfigEntry,ConfigEntryState,SOURCE_USER
from homeassistant.helpers import entity_registry as er
from homeassistant.const import CONF_PASSWORD,CONF_TOKEN
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, Unauthorized

from custom_components.defro_emodul.api import Authentication,EmodulApi
from custom_components.defro_emodul.const import DOMAIN
from custom_components.defro_emodul.diagnostics import async_get_config_entry_diagnostics


def entry():
    return ConfigEntry(version=1,minor_version=1,domain=DOMAIN,title='DEFRO APC Slim',
        source=SOURCE_USER,unique_id='controller-uuid',discovery_keys={},subentries_data=None,options={},
        data={'site':'emodul.pl','user_id':'42','token':'private-session-token','module_udid':'controller-uuid','menu_codes':{'MS':'1234'}})


async def test_real_homeassistant_registers_all_317_and_updates(hass,monkeypatch,snapshot):
    fetch=AsyncMock(return_value=copy.deepcopy(snapshot))
    monkeypatch.setattr(EmodulApi,'async_snapshot',fetch)
    item=entry()
    await hass.config_entries.async_add(item)
    await hass.async_block_till_done()
    assert item.state is ConfigEntryState.LOADED,item.state
    registry=er.async_get(hass)
    entries=er.async_entries_for_config_entry(registry,item.entry_id)
    assert len([e for e in entries if e.domain in ('sensor','binary_sensor')])==317
    assert {e.domain for e in entries}=={'sensor','binary_sensor','number','select','switch'}
    assert len(entries)>317
    assert all(e.disabled_by is None for e in entries)
    assert sum(e.domain=='sensor' for e in entries)==261
    assert sum(e.domain=='binary_sensor' for e in entries)==56
    assert all(hass.states.get(e.entity_id) is not None for e in entries)
    co=next(e for e in entries if e.unique_id.endswith(':tile_1006_value'))
    pump=next(e for e in entries if e.unique_id.endswith(':tile_1004_workingstatus'))
    assert hass.states.get(co.entity_id).state=='60.5'
    assert hass.states.get(pump.entity_id).state=='on'
    changed=copy.deepcopy(snapshot)
    changed['sections']['tile']['elements'][1006]['params']['value']=715
    changed['sections']['tile']['elements'][1004]['params']['workingStatus']=False
    item.runtime_data.async_set_updated_data(changed)
    await hass.async_block_till_done()
    assert hass.states.get(co.entity_id).state=='71.5'
    assert hass.states.get(pump.entity_id).state=='off'
    changed['online']=False
    item.runtime_data.async_set_updated_data(changed)
    await hass.async_block_till_done()
    assert hass.states.get(co.entity_id).state=='unavailable'
    diag=await async_get_config_entry_diagnostics(hass,item)
    assert diag['catalogue_entities']==317
    serialized=str(diag)
    assert 'private-session-token' not in serialized and '1234' not in serialized and 'controller-uuid' not in serialized


async def test_ui_flow_stores_token_not_password_and_reauth_preserves_entities(hass,monkeypatch,snapshot):
    next_token={'value':'first-session-token'}
    async def authenticate(self,username,password):
        self.authentication=Authentication('42',next_token['value'])
        return self.authentication
    monkeypatch.setattr(EmodulApi,'async_authenticate',authenticate)
    monkeypatch.setattr(EmodulApi,'async_modules',AsyncMock(return_value=[{
        'udid':'controller-uuid','name':'DEFRO APC Slim','type':'pellet','company':'defro','version':'Defro ST-9730',
    }]))
    monkeypatch.setattr(EmodulApi,'async_snapshot',AsyncMock(return_value=copy.deepcopy(snapshot)))
    result=await hass.config_entries.flow.async_init(DOMAIN,context={'source':SOURCE_USER})
    assert result['step_id']=='user'
    result=await hass.config_entries.flow.async_configure(result['flow_id'],{
        'site':'emodul.pl','username':'owner@example.com','password':'only-in-the-form',
    })
    assert result['step_id']=='module'
    result=await hass.config_entries.flow.async_configure(result['flow_id'],{
        'module_udid':'controller-uuid','service_code':'1234',
    })
    assert result['type']=='create_entry'
    item=result['result']
    await hass.async_block_till_done()
    assert item.state is ConfigEntryState.LOADED
    assert CONF_PASSWORD not in item.data
    assert 'username' not in item.data
    assert 'only-in-the-form' not in str(item.data)
    ids_before={x.entity_id for x in er.async_entries_for_config_entry(er.async_get(hass),item.entry_id)}
    assert len(ids_before)>317
    next_token['value']='new-session-token'
    reauth=await hass.config_entries.flow.async_init(DOMAIN,context={'source':'reauth','entry_id':item.entry_id},data=dict(item.data))
    assert reauth['step_id']=='reauth_confirm'
    done=await hass.config_entries.flow.async_configure(reauth['flow_id'],{'username':'owner@example.com','password':'new-private-password'})
    assert done['type']=='abort' and done['reason']=='reauth_successful'
    await hass.async_block_till_done()
    assert item.data[CONF_TOKEN]=='new-session-token'
    assert len(hass.config_entries.async_entries(DOMAIN))==1
    assert ids_before=={x.entity_id for x in er.async_entries_for_config_entry(er.async_get(hass),item.entry_id)}


async def test_reconfigure_updates_menu_access_without_new_entities(hass,monkeypatch,snapshot):
    monkeypatch.setattr(EmodulApi,'async_snapshot',AsyncMock(return_value=copy.deepcopy(snapshot)))
    monkeypatch.setattr(EmodulApi,'async_menu',AsyncMock(return_value={'status':'ok','elements':{}}))
    item=entry();await hass.config_entries.async_add(item);await hass.async_block_till_done()
    ids={x.entity_id for x in er.async_entries_for_config_entry(er.async_get(hass),item.entry_id)}
    flow=await hass.config_entries.flow.async_init(DOMAIN,context={'source':'reconfigure','entry_id':item.entry_id})
    assert flow['step_id']=='reconfigure'
    done=await hass.config_entries.flow.async_configure(flow['flow_id'],{'service_code':'5678'})
    assert done['type']=='abort' and done['reason']=='reconfigure_successful'
    await hass.async_block_till_done()
    assert item.data['menu_codes']=={'MS':'5678'}
    assert ids=={x.entity_id for x in er.async_entries_for_config_entry(er.async_get(hass),item.entry_id)}


async def test_expired_cloud_session_starts_reauth(hass,monkeypatch,snapshot):
    from custom_components.defro_emodul.api import AuthError
    fetch=AsyncMock(return_value=copy.deepcopy(snapshot))
    monkeypatch.setattr(EmodulApi,'async_snapshot',fetch)
    item=entry();await hass.config_entries.async_add(item);await hass.async_block_till_done()
    fetch.side_effect=AuthError('invalid_auth')
    await item.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flows=hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(flow['context'].get('source')=='reauth' for flow in flows)
    assert item.runtime_data.last_update_success is False
    panel=await hass.services.async_call(DOMAIN,'get_controls',{},blocking=True,return_response=True)
    controller=panel['controllers'][0]
    assert not controller['online']
    assert all(not c['available'] and not c['can_unlock'] for c in controller['controls'])
    assert all(t['value'] is None for t in controller['tiles'])


async def setup_controller(hass,monkeypatch,snapshot):
    fetch=AsyncMock(return_value=copy.deepcopy(snapshot))
    write=AsyncMock()
    monkeypatch.setattr(EmodulApi,'async_snapshot',fetch)
    monkeypatch.setattr(EmodulApi,'async_set_menu',write)
    item=entry();await hass.config_entries.async_add(item);await hass.async_block_till_done()
    registry=er.async_get(hass)
    entities=er.async_entries_for_config_entry(registry,item.entry_id)
    return item,fetch,write,entities


async def test_panel_tiles_resolve_registered_entities_and_follow_user_renames(hass,monkeypatch,snapshot):
    item,_,write,entities=await setup_controller(hass,monkeypatch,snapshot)
    registry=er.async_get(hass)
    temperature=next(e for e in entities if e.unique_id.endswith(':tile_1006_value'))
    renamed=registry.async_update_entity(temperature.entity_id,new_entity_id='sensor.moja_temperatura_kotla')
    await hass.async_block_till_done()
    response=await hass.services.async_call(DOMAIN,'get_controls',{},blocking=True,return_response=True)
    tiles=response['controllers'][0]['tiles']
    assert next(t for t in tiles if t['key']=='tile_1006_value')['entity_id']==renamed.entity_id
    pump_tile=next(t for t in tiles if t['key']=='tile_1004_workingstatus')
    assert pump_tile['animation']=='pump' and pump_tile['active'] is True
    assert next(t for t in tiles if t['key']=='tile_1011_gear')['animation']=='fan'
    assert next(t for t in tiles if t['key']=='tile_1012_valvepump')['icon']=='mdi:pump'
    assert next(t for t in tiles if t['key']=='tile_1006_value')['animation']==''
    for tile in tiles:
        registered=registry.async_get(tile['entity_id'])
        assert registered.config_entry_id==item.entry_id
        assert registered.unique_id=='controller-uuid:'+tile['key']
        assert hass.states.get(tile['entity_id']) is not None
    assert any(t['entity_id'].startswith('binary_sensor.') for t in tiles)
    assert hass.states.get(renamed.entity_id).attributes['state_class']=='measurement'
    assert hass.states.get(renamed.entity_id).attributes['device_class']=='temperature'
    item.runtime_data.last_update_success=False
    offline=await hass.services.async_call(DOMAIN,'get_controls',{},blocking=True,return_response=True)
    assert next(t for t in offline['controllers'][0]['tiles'] if t['key']=='tile_1006_value')['entity_id']==renamed.entity_id
    assert all(t['active'] is False for t in offline['controllers'][0]['tiles'])
    write.assert_not_awaited()


@pytest.mark.parametrize('key,domain,service,data,payload',[
    ('mu_2060','number','set_value',{'value':71},{'value':71}),
    ('mu_2089','number','set_value',{'value':21.7},{'value':217}),
    ('mu_2011','select','select_option',{'option':'Tryb letni'},{'value':3}),
    ('mu_30046','switch','turn_on',{}, {'value':1}),
    ('mi_30281_option_0','switch','turn_on',{}, {'many_of_many':[{'id':0,'value':1},{'id':1,'value':0}]}),
    ('mi_2217_point_-20','number','set_value',{'value':65},{'heating_curve':[{'id':0,'value':65},{'id':1,'value':55},{'id':2,'value':50},{'id':3,'value':45}]}),
])
async def test_real_ha_control_services_send_one_validated_command(hass,monkeypatch,snapshot,key,domain,service,data,payload):
    item,fetch,write,entities=await setup_controller(hass,monkeypatch,snapshot)
    target=next(e for e in entities if e.unique_id=='controller-uuid:control:'+key)
    await hass.services.async_call(domain,service,{'entity_id':target.entity_id,**data},blocking=True)
    assert write.await_count==1
    args=write.call_args.args
    assert args[-1]==payload
    assert fetch.call_args.kwargs=={'force_menus':True}
    await hass.async_block_till_done()
    assert hass.states.get(target.entity_id).state=='unavailable'
    assert item.runtime_data._pending


async def test_current_cloud_access_is_checked_before_writing(hass,monkeypatch,snapshot):
    item,fetch,write,_=await setup_controller(hass,monkeypatch,snapshot)
    changed=copy.deepcopy(snapshot)
    changed['sections']['MU']['elements'][2060]['access']=False
    fetch.return_value=changed
    with pytest.raises(HomeAssistantError):await item.runtime_data.async_write_control('mu_2060',71)
    write.assert_not_awaited()


async def test_pending_change_needs_matching_readback_and_cannot_be_sent_twice(hass,monkeypatch,snapshot):
    item,fetch,write,_=await setup_controller(hass,monkeypatch,snapshot)
    co=item.runtime_data
    await co.async_write_control('mu_2060',71)
    with pytest.raises(HomeAssistantError):await co.async_write_control('mu_2060',72)
    assert write.await_count==1
    await co.async_refresh()
    assert 'mu_2060' in co._pending and not co.controls['mu_2060']['available']
    changed=copy.deepcopy(snapshot)
    changed['sections']['MU']['elements'][2060]['params']['value']=71
    fetch.return_value=changed
    await co.async_refresh()
    assert not co._pending
    assert co.controls['mu_2060']['value']==71 and co.controls['mu_2060']['available']


async def test_missing_write_confirmation_gives_warning_instead_of_optimistic_value(hass,monkeypatch,snapshot):
    item,fetch,_,_=await setup_controller(hass,monkeypatch,snapshot)
    co=item.runtime_data
    await co.async_write_control('mu_2060',71)
    co._pending['mu_2060']['expires']=monotonic()-1
    await co.async_refresh()
    assert not co._pending and 'mu_2060' in co.write_errors
    assert co.controls['mu_2060']['value']==60


async def test_write_auth_failure_starts_reauth_without_repeating_post(hass,monkeypatch,snapshot):
    from custom_components.defro_emodul.api import AuthError
    item,_,write,_=await setup_controller(hass,monkeypatch,snapshot)
    write.side_effect=AuthError('invalid_auth')
    with pytest.raises(HomeAssistantError):await item.runtime_data.async_write_control('mu_2060',71)
    assert write.await_count==1 and not item.runtime_data._pending
    await hass.async_block_till_done()
    assert any(f['context'].get('source')=='reauth' for f in hass.config_entries.flow.async_progress_by_handler(DOMAIN))


async def test_panel_services_cover_complex_types_and_omit_credentials(hass,monkeypatch,snapshot):
    item,_,write,_=await setup_controller(hass,monkeypatch,snapshot)
    response=await hass.services.async_call(DOMAIN,'get_controls',{},blocking=True,return_response=True)
    controller=response['controllers'][0]
    assert controller['entry_id']==item.entry_id
    assert {'schedule_offset','schedule_onoff','curve','checkbox','action','password'}<={c['kind'] for c in controller['controls']}
    assert all(secret not in str(response) for secret in ('private-session-token','controller-uuid','menu_codes',"'password':",'user_id'))
    target=next(c for c in controller['controls'] if c['kind']=='schedule_offset')
    await hass.services.async_call(DOMAIN,'set_parameter',{
        'entry_id':item.entry_id,'key':target['key'],'value':[-2]*24},blocking=True)
    assert write.call_args.args[-1]=={'weekly_plus_minus':{'values':[23]*24}}


async def test_panel_denies_non_admin_access(hass,monkeypatch,snapshot):
    await setup_controller(hass,monkeypatch,snapshot)
    monkeypatch.setattr(hass,'auth',SimpleNamespace(async_get_user=AsyncMock(return_value=SimpleNamespace(is_admin=False))),raising=False)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(DOMAIN,'get_controls',{},context=Context(user_id='not-admin'),blocking=True,return_response=True)


async def test_unlock_stores_known_code_locally_without_exposing_it_in_panel(hass,monkeypatch,snapshot):
    item,fetch,_,_=await setup_controller(hass,monkeypatch,snapshot)
    async def unlock(self,udid,section,element_id,code):
        self.menu_item_codes.setdefault(section,{})[str(element_id)]=code
    monkeypatch.setattr(EmodulApi,'async_unlock_menu',unlock)
    await hass.services.async_call(DOMAIN,'unlock_menu',{
        'entry_id':item.entry_id,'key':'ms_30414','code':'987654'},blocking=True)
    assert item.data['menu_item_codes']=={'MS':{'30414':'987654'}}
    assert item.data['menu_item_codes'] is not item.runtime_data.api.menu_item_codes
    assert item.data['menu_item_codes']['MS'] is not item.runtime_data.api.menu_item_codes['MS']
    response=await hass.services.async_call(DOMAIN,'get_controls',{},blocking=True,return_response=True)
    assert '987654' not in str(response)


async def test_reconfigure_can_clear_expired_submenu_codes(hass,monkeypatch,snapshot):
    monkeypatch.setattr(EmodulApi,'async_snapshot',AsyncMock(return_value=copy.deepcopy(snapshot)))
    monkeypatch.setattr(EmodulApi,'async_menu',AsyncMock(return_value={'status':'ok','elements':{}}))
    item=entry()
    await hass.config_entries.async_add(item);await hass.async_block_till_done()
    hass.config_entries.async_update_entry(item,data={**item.data,'menu_item_codes':{'MS':{'30414':'987654'}}})
    flow=await hass.config_entries.flow.async_init(DOMAIN,context={'source':'reconfigure','entry_id':item.entry_id})
    result=await hass.config_entries.flow.async_configure(flow['flow_id'],{'service_code':'1234','clear_submenu_codes':True})
    assert result['type']=='abort' and result['reason']=='reconfigure_successful'
    await hass.async_block_till_done()
    assert item.data['menu_codes']=={'MS':'1234'} and item.data['menu_item_codes']=={}


async def test_cloud_rate_limit_stops_writes_during_poll_backoff(hass,monkeypatch,snapshot):
    from custom_components.defro_emodul.api import RateLimitError
    item,fetch,write,_=await setup_controller(hass,monkeypatch,snapshot)
    fetch.side_effect=RateLimitError('rate_limit')
    await item.runtime_data.async_refresh()
    count=fetch.await_count
    with pytest.raises(HomeAssistantError):await item.runtime_data.async_write_control('mu_2060',71)
    assert fetch.await_count==count
    write.assert_not_awaited()



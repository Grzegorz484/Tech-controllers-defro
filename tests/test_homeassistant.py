import copy
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntry,ConfigEntryState,SOURCE_USER
from homeassistant.helpers import entity_registry as er
from homeassistant.const import CONF_PASSWORD,CONF_TOKEN

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
    assert len(entries)==317
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
    assert len(ids_before)==317
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



from time import monotonic
from types import SimpleNamespace

import aiohttp
from aioresponses import aioresponses as BaseResponses
import pytest

from custom_components.defro_emodul.api import ApiError,AuthError,Authentication,EmodulApi,RateLimitError

BASE='https://emodul.pl/api/v1'
MOD='/users/42/modules/controller-uuid'
MODULE={'udid':'controller-uuid','name':'DEFRO','type':'pellet','company':'defro','version':'Defro: ST-9730','controllerStatus':'active','moduleStatus':'active'}


class CompatibleResponse(aiohttp.ClientResponse):
    """aioresponses 0.7.9 predates aiohttp 3.14's required constructor argument."""
    def __init__(self,*args,**kwargs):
        kwargs.setdefault('stream_writer',SimpleNamespace(output_size=0))
        super().__init__(*args,**kwargs)


class aioresponses(BaseResponses):
    def add(self,*args,**kwargs):
        kwargs.setdefault('response_class',CompatibleResponse)
        return super().add(*args,**kwargs)


async def test_auth_and_reads_only_and_profile_is_filtered():
    async with aiohttp.ClientSession() as session:
        api=EmodulApi(session,'emodul.pl')
        with aioresponses() as net:
            net.post(BASE+'/authentication',payload={'authenticated':True,'token':'private-session-token','user_id':42})
            net.get(BASE+'/users/42/modules',payload=[{**MODULE,'email':'owner@example.com','phoneNumber':'123456789'}])
            auth=await api.async_authenticate('owner','private-password')
            modules=await api.async_modules()
            assert 'email' not in modules[0] and 'phoneNumber' not in modules[0]
            assert 'private-session-token' not in repr(auth)
            assert list(net.requests)[0][0]=='POST' and list(net.requests)[1][0]=='GET'
            for method in ('POST','PUT','PATCH','DELETE'):
                with pytest.raises(ApiError,match='write_blocked'):
                    await api._request(method,MOD+'/zones',{'value':25})
            assert len(net.requests)==2


async def test_redirect_does_not_forward_token_or_follow_location():
    async with aiohttp.ClientSession() as session:
        api=EmodulApi(session,'emodul.pl',Authentication('42','private-session-token'))
        with aioresponses() as net:
            net.get(BASE+'/users/42/modules',status=302,headers={'Location':'https://evil.example/collect'})
            with pytest.raises(ApiError) as exc:await api.async_modules()
            assert exc.value.status==302
            assert len(net.requests)==1
            assert 'private-session-token' not in str(exc.value)


async def test_menu_unlock_uses_one_known_code_in_get_only():
    async with aiohttp.ClientSession() as session:
        api=EmodulApi(session,'emodul.pl',Authentication('42','token'),menu_codes={'MS':'1234'})
        with aioresponses() as net:
            net.get(BASE+MOD+'/menu/MS/',payload={'data':{'elements':[{'id':0,'params':{'password':'password'}}]}})
            net.get(BASE+MOD+'/menu/MS/0:1234',payload={'data':{'elements':[{'id':2086,'type':1,'params':{'value':40}}]}})
            result=await api.async_menu('controller-uuid','MS')
            assert result['status']=='ok' and result['elements'][2086]['params']['value']==40
            assert all(method=='GET' for method,url in net.requests)
            assert len(net.requests)==2


async def test_invalid_code_and_rate_limit_are_explicit():
    async with aiohttp.ClientSession() as session:
        api=EmodulApi(session,'emodul.pl',Authentication('42','token'),menu_codes={'MS':'1234'})
        with aioresponses() as net:
            net.get(BASE+MOD+'/menu/MS/',payload={'data':{'elements':[{'id':0,'params':{'password':'password'}}]}})
            net.get(BASE+MOD+'/menu/MS/0:1234',status=422,body='private server data')
            assert (await api.async_menu('controller-uuid','MS'))['status']=='invalid_code'
        with aioresponses() as net:
            net.get(BASE+'/users/42/modules',status=429)
            with pytest.raises(RateLimitError):await api.async_modules()


async def test_offline_stops_before_fetching_cached_readings():
    async with aiohttp.ClientSession() as session:
        api=EmodulApi(session,'emodul.pl',Authentication('42','token'))
        with aioresponses() as net:
            net.get(BASE+'/users/42/modules',payload=[{**MODULE,'controllerStatus':'inactive'}])
            data=await api.async_snapshot('controller-uuid')
            assert data['online'] is False and data['sections']=={}
            assert len(net.requests)==1


async def test_failed_menu_drops_stale_cache_and_retries_next_poll():
    async with aiohttp.ClientSession() as session:
        api=EmodulApi(session,'emodul.pl',Authentication('42','token'))
        api._last_translation_attempt=monotonic()
        old={'status':'ok','elements':{2060:{'id':2060,'params':{'value':70}}}}
        api._menu_cache={'MU':(monotonic()-600,old)}
        with aioresponses() as net:
            net.get(BASE+'/users/42/modules',payload=[MODULE],repeat=True)
            net.get(BASE+MOD,payload={'tiles':[]},repeat=True)
            net.get(BASE+MOD+'/menu/MU/',status=503)
            for menu in ('MI','MS'):net.get(BASE+MOD+'/menu/'+menu+'/',payload={'data':{'elements':[]}})
            first=await api.async_snapshot('controller-uuid')
            assert first['sections']['MU']['status']=='error'
            assert first['sections']['MU']['elements']=={}
            net.get(BASE+MOD+'/menu/MU/',payload={'data':{'elements':[{'id':2060,'type':1,'params':{'value':71}}]}})
            second=await api.async_snapshot('controller-uuid')
            assert second['sections']['MU']['elements'][2060]['params']['value']==71


async def test_bad_auth_does_not_persist_a_session():
    async with aiohttp.ClientSession() as session:
        api=EmodulApi(session,'emodul.pl')
        with aioresponses() as net:
            net.post(BASE+'/authentication',payload={'authenticated':False})
            with pytest.raises(AuthError):await api.async_authenticate('owner','not-recorded')
            assert api.authentication is None


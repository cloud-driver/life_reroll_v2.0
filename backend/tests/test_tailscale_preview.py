"""The phone preview binds a Tailscale address without widening to LAN/public interfaces."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('training_tail_preview',Path(__file__).parents[2]/'scripts/training-tailscale.py')
preview=importlib.util.module_from_spec(spec);spec.loader.exec_module(preview)

@pytest.mark.parametrize('state,ips',[('Stopped',['100.111.84.94']),('NeedsLogin',[]),('Running',['127.0.0.1']),('Running',['192.168.10.200']),('Running',['0.0.0.0']),('Running',['100.128.1.1'])])
def test_preview_never_chooses_an_unconnected_or_non_tailnet_address(state,ips):
 with pytest.raises(ValueError):preview.tailscale_ip({'BackendState':state,'TailscaleIPs':ips})

def test_connected_tailnet_address_works_without_https_admin_changes():
 assert preview.tailscale_ip({'BackendState':'Running','TailscaleIPs':['fd7a:115c:a1e0::123','100.111.84.94']})=='100.111.84.94'

def test_phone_command_check_has_no_server_or_config_side_effect(monkeypatch,capsys):
 monkeypatch.setattr(preview,'detect_ip',lambda:'100.111.84.94')
 monkeypatch.setattr(preview.os,'execv',lambda *_:pytest.fail('check must not start a server'))
 monkeypatch.setattr(preview.sys,'argv',['preview','--check'])
 assert preview.main()==0 and capsys.readouterr().out.strip()=='100.111.84.94'

#!/usr/bin/env python3
from mn_wifi.net import Mininet_wifi
from mn_wifi.node import OVSKernelAP
from mn_wifi.cli import CLI   # <-- use CLI, not CLI_wifi on 2.6
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info

import json
import os

def load_link_delays(json_path, directed=False):
    """
    Read links.json as a list of {name,u,v,delay_ms} and build a lookup.
    If directed=False (default), u-v and v-u share the same delay.
    Returns: function delay(u, v) -> 'Xms' (string) or '0ms' if missing.
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"links.json not found at: {json_path}")

    with open(json_path) as f:
        data = json.load(f)

    # Validate and build map
    if not isinstance(data, list):
        raise ValueError("links.json must be a JSON array")

    if directed:
        # key is (u,v) exactly
        lut = {}
        for L in data:
            for k in ("u", "v", "delay_ms"):
                if k not in L:
                    raise ValueError(f"links.json entry missing '{k}': {L}")
            key = (L["u"], L["v"])
            lut[key] = f"{int(L['delay_ms'])}ms"
        def get_delay(u, v, default="0ms"):
            return lut.get((u, v), default)
    else:
        # undirected: key is frozenset({u,v})
        lut = {}
        for L in data:
            for k in ("u", "v", "delay_ms"):
                if k not in L:
                    raise ValueError(f"links.json entry missing '{k}': {L}")
            key = frozenset((L["u"], L["v"]))
            lut[key] = f"{int(L['delay_ms'])}ms"
        def get_delay(u, v, default="0ms"):
            return lut.get(frozenset((u, v)), default)

    return get_delay


def run():

    delay_for = load_link_delays('links.json', directed=False)
    setLogLevel('info')
    net = Mininet_wifi(controller=None, link=TCLink, switch=OVSKernelSwitch)

    # Controller (RYU simple_switch_13 listens on 6633 below)
    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6633)

    # Hosts
    pc1 = net.addHost('pc1', ip='10.0.0.1/24')
    pc2 = net.addHost('pc2', ip='10.0.0.2/24')
    pc5 = net.addHost('pc5', ip='10.0.0.5/24')
    pc6 = net.addHost('pc6', ip='10.0.0.6/24')

    # Stations
    pc3 = net.addStation('pc3', wlans=1, position='10,20,0', ip='10.0.0.3/24', ssid='ssid-ap1')
    pc4 = net.addStation('pc4', wlans=1, position='10,40,0', ip='10.0.0.4/24', ssid='ssid-ap2')

    # Switches
    sw1 = net.addSwitch('sw1', protocols='OpenFlow13')
    sw2 = net.addSwitch('sw2', protocols='OpenFlow13')
    sw3 = net.addSwitch('sw3', protocols='OpenFlow13')
    sw4 = net.addSwitch('sw4', protocols='OpenFlow13')

    # APs
    ap1 = net.addAccessPoint('ap1', cls=OVSKernelAP, ssid='ssid-ap1', mode='g', channel='1',
                             protocols='OpenFlow13', failMode='secure', position='10,20,0')
    ap2 = net.addAccessPoint('ap2', cls=OVSKernelAP, ssid='ssid-ap2', mode='g', channel='6',
                             protocols='OpenFlow13', failMode='secure', position='10,40,0')

    # Wireless model
    net.setPropagationModel(model="logDistance", exp=3.5)
    net.configureWifiNodes()

    # Links (no explicit port numbers)
    net.addLink(pc1, sw1, port1=1, port2=1, cls=TCLink, delay=delay_for('pc1', 'sw1'))
    net.addLink(pc2, sw3, port1=1, port2=1, cls=TCLink, delay=delay_for('pc2', 'sw3'))
    net.addLink(pc5, sw2, port1=1, port2=1, cls=TCLink, delay=delay_for('pc5', 'sw2'))
    net.addLink(pc6, sw4, port1=1, port2=1, cls=TCLink, delay=delay_for('pc6', 'sw4'))

    net.addLink(sw1, sw2, port1=2, port2=2, cls=TCLink, delay=delay_for('sw1', 'sw2'))
    net.addLink(sw1, sw3, port1=3, port2=3, cls=TCLink, delay=delay_for('sw1', 'sw3'))
    net.addLink(sw3, sw4, port1=2, port2=2, cls=TCLink, delay=delay_for('sw3', 'sw4'))
    # Break below link for now, untill proper controller is setup.
    net.addLink(sw4, sw2, port1=3, port2=3, cls=TCLink, delay=delay_for('sw4', 'sw2'))
    net.addLink(sw1, sw4, port1=5, port2=5, cls=TCLink, delay=delay_for('sw1', 'sw4'))
    net.addLink(sw2, sw3, port1=4, port2=4, cls=TCLink, delay=delay_for('sw2', 'sw3'))

    # Backhaul (APs into the switch fabric)
    net.addLink(sw1, ap2, cls=TCLink, delay=delay_for('sw1', 'ap2'))
    net.addLink(sw4, ap1, cls=TCLink, delay=delay_for('sw4', 'ap1'))


    net.build()
    c0.start()

    # Ensure OF1.3 everywhere and start with controller
    for b in (sw1, sw2, sw3, sw4, ap1, ap2):
        b.cmd(f'ovs-vsctl set Bridge {b.name} protocols=OpenFlow13')
        b.start([c0])

    # --- Force pc4 to associate with ap2 after startup ---
    info('*** Forcing pc4 to disconnect from any AP and connect to ap2\n')
    pc4.cmd('iw dev pc4-wlan0 disconnect')
    pc4.cmd('sleep 1')
    pc4.cmd('iw dev pc4-wlan0 connect ssid-ap2')
    pc4.cmd('sleep 1')
    info(pc4.cmd('iw dev pc4-wlan0 link'))

    
    CLI(net)
    net.stop()

if __name__ == '__main__':
    run()

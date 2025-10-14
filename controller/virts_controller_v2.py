from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib.packet import ipv4 as ipv4_pkt
from ryu.lib.packet import ipv6 as ipv6_pkt  # optional
from ryu.lib.packet import arp as arp_pkt


import json
from ryu.lib import hub
import os, subprocess

DROP_PRIO = 500

class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self._broken_letters = set()     # tracks which link letters are currently broken
        self._baseline_done = False      # apply "break all links" baseline once
        here = os.path.dirname(os.path.abspath(__file__))
        self.dijkstra_script = os.path.normpath(os.path.join(here, "..", "algorithm", "virts_dijkstra.py"))

        self._printed_routes = set()
        self._ip2node = {
            "10.0.0.1": "pc1",
            "10.0.0.2": "pc2",
            "10.0.0.3": "pc3",
            "10.0.0.4": "pc4",
            "10.0.0.5": "pc5",
            "10.0.0.6": "pc6",
        }
        self.mac_to_port = {}
        self.dp_map = {}

    # -------- Utility: build mirrored actions for installed flows --------
    def _mirror_actions(self, parser, ofproto, out_port):
        return [
            parser.OFPActionOutput(out_port),
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)
        ]

    # -------- Utility: add flow (supports idle_timeout) --------
    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst, idle_timeout=idle_timeout)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst,
                                    idle_timeout=idle_timeout)
        datapath.send_msg(mod)

    # -------- Utilities: delete/insert high-priority drop on in_port --------
    def _drop_inport(self, dp, in_port, priority=DROP_PRIO):
        p = dp.ofproto_parser
        self.add_flow(dp, priority=priority, match=p.OFPMatch(in_port=in_port), actions=[])

    def _del_inport_drop(self, dp, in_port, priority=DROP_PRIO):
        ofp = dp.ofproto
        p = dp.ofproto_parser
        msg = p.OFPFlowMod(datapath=dp,
                           command=ofp.OFPFC_DELETE,
                           out_port=ofp.OFPP_ANY,
                           out_group=ofp.OFPG_ANY,
                           priority=priority,
                           match=p.OFPMatch(in_port=in_port))
        dp.send_msg(msg)

    def _restore_inport(self, dpid, port):
        dp = self.dp_map.get(dpid)
        if not dp:
            self.logger.warning("DPID %s not connected; cannot restore port %s", dpid, port)
            return
        self._del_inport_drop(dp, port)

    # -------- Link restore functions (per letter) --------
    def _restore_link_A(self):
        dp1, dp2 = self.dp_map.get(1), self.dp_map.get(2)
        if dp1: self._del_inport_drop(dp1, 2)
        if dp2: self._del_inport_drop(dp2, 2)

    def _restore_link_B(self):
        dp1, dp3 = self.dp_map.get(1), self.dp_map.get(3)
        if dp1: self._del_inport_drop(dp1, 3)
        if dp3: self._del_inport_drop(dp3, 3)

    def _restore_link_C(self):
        dp3, dp4 = self.dp_map.get(3), self.dp_map.get(4)
        if dp3: self._del_inport_drop(dp3, 2)
        if dp4: self._del_inport_drop(dp4, 2)

    def _restore_link_D(self):
        dp2, dp4 = self.dp_map.get(2), self.dp_map.get(4)
        if dp2: self._del_inport_drop(dp2, 3)
        if dp4: self._del_inport_drop(dp4, 3)

    def _restore_link_E(self):
        dp2, dp3 = self.dp_map.get(2), self.dp_map.get(3)
        if dp2: self._del_inport_drop(dp2, 4)
        if dp3: self._del_inport_drop(dp3, 4)

    def _restore_link_F(self):
        dp1, dp4 = self.dp_map.get(1), self.dp_map.get(4)
        if dp1: self._del_inport_drop(dp1, 5)
        if dp4: self._del_inport_drop(dp4, 5)

    def _restore_all_links(self):
        self._restore_link_A(); self._restore_link_B(); self._restore_link_C()
        self._restore_link_D(); self._restore_link_E(); self._restore_link_F()
        self._broken_letters.clear()

    # -------- Link break functions (per letter) --------
    def break_link_A(self):
        dp1, dp2 = self.dp_map.get(1), self.dp_map.get(2)
        if dp1: self._drop_inport(dp1, 2)
        if dp2: self._drop_inport(dp2, 2)

    def break_link_B(self):
        dp1, dp3 = self.dp_map.get(1), self.dp_map.get(3)
        if dp1: self._drop_inport(dp1, 3)
        if dp3: self._drop_inport(dp3, 3)

    def break_link_C(self):
        dp3, dp4 = self.dp_map.get(3), self.dp_map.get(4)
        if dp3: self._drop_inport(dp3, 2)
        if dp4: self._drop_inport(dp4, 2)

    def break_link_D(self):
        dp2, dp4 = self.dp_map.get(2), self.dp_map.get(4)
        if dp2: self._drop_inport(dp2, 3)
        if dp4: self._drop_inport(dp4, 3)

    def break_link_E(self):
        dp2, dp3 = self.dp_map.get(2), self.dp_map.get(3)
        if dp2: self._drop_inport(dp2, 4)
        if dp3: self._drop_inport(dp3, 4)

    def break_link_F(self):
        dp1, dp4 = self.dp_map.get(1), self.dp_map.get(4)
        if dp1: self._drop_inport(dp1, 5)
        if dp4: self._drop_inport(dp4, 5)

    def _break_all_links(self):
        # One-time baseline: break ALL inter-switch links
        self.break_link_A(); self.break_link_B(); self.break_link_C()
        self.break_link_D(); self.break_link_E(); self.break_link_F()
        self._broken_letters |= {"A","B","C","D","E","F"}
        self.logger.info("Baseline applied: all inter-switch links broken")

    # -------- Dijkstra runner + parsing --------
    def _run_path(self, src_node: str, dst_node: str):
        """Run Dijkstra synchronously and return string."""
        try:
            out = subprocess.check_output(
                ["python3", self.dijkstra_script, src_node, dst_node],
                stderr=subprocess.STDOUT, timeout=10,
            ).decode(errors="ignore").strip()
            self.logger.info("[Dijkstra] %s", out)
            return out
        except subprocess.CalledProcessError as e:
            self.logger.error("[Dijkstra] rc=%s: %s", e.returncode, e.output.decode(errors="ignore"))
        except Exception as e:
            self.logger.error("[Dijkstra] error: %r", e)
        return None

    def _shortest_path_switches(self, src_node: str, dst_node: str) -> list | None:
        """Return ['swX','swY', ...] parsed from the 'nodes:' line."""
        out = self._run_path(src_node, dst_node)
        if not out:
            return None
        nodes_line = next((ln for ln in out.splitlines() if "nodes:" in ln.lower()), None)
        if not nodes_line:
            return None
        inside = nodes_line.split("nodes:", 1)[1]
        inside = inside.split("(", 1)[0].strip()
        inside = inside.replace("->", ",")
        nodes = [n.strip() for n in inside.split(",") if n.strip()]
        switches = [n for n in nodes if n.lower().startswith("sw")]
        return switches

    def _ensure_names_index(self):
        """Load names.json once and build a fast (u,v)->name index (both directions)."""
        if hasattr(self, "_pair_to_name"):
            return
        here = os.path.dirname(os.path.abspath(__file__))
        names_path = os.path.normpath(os.path.join(here, "..", "topology", "names.json"))
        with open(names_path, "r") as f:
            data = json.load(f)
        self._pair_to_name = {}
        for item in data:
            nodesf = tuple(x.strip().lower() for x in item["nodesf"].split(","))
            nodesr = tuple(x.strip().lower() for x in item["nodesr"].split(","))
            self._pair_to_name[nodesf] = item["name"]
            self._pair_to_name[nodesr] = item["name"]

    def _switches_to_link_names(self, switches: list[str]) -> list[str]:
        """Given ['sw1','sw3','sw4'] return ['B','C'] by looking up each adjacent pair."""
        self._ensure_names_index()
        names = []
        sw_lc = [s.strip().lower() for s in switches if s]
        for a, b in zip(sw_lc, sw_lc[1:]):
            names.append(self._pair_to_name.get((a, b), None))
        return [n for n in names if n]

    def _call_link_fn(self, prefix: str, letter: str):
        
        fn_name = f"{prefix}_link_{letter}"
        fn = getattr(self, fn_name, None)
        if callable(fn):
            fn()
        else:
            self.logger.error("Missing method: %s", fn_name)

    def _apply_link_policy(self, keep_letters):
        """
        keep_letters: iterable of link letters to KEEP (e.g., ['B','C']).
        Breaks all other links, restores the kept ones if needed.
        """
        ALL = {'A','B','C','D','E','F'}
        keep = set(keep_letters or [])
        to_break = ALL - keep
        to_restore = keep

        self.logger.info("Policy keep=%s break=%s", sorted(keep), sorted(to_break))

        # Restore anything we want to keep (if currently broken)
        for L in to_restore:
            if L in self._broken_letters:
                self._call_link_fn('_restore', L)
                self._broken_letters.discard(L)
                self.logger.info("Restored link %s", L)

        # Break everything else (if not already broken)
        for L in to_break:
            if L not in self._broken_letters:
                self._call_link_fn('break', L)
                self._broken_letters.add(L)
                self.logger.info("Broke link %s", L)

    # -------- Switch features handler --------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # store datapath for later cross-programming
        self.dp_map[datapath.id] = datapath
        self.logger.info("[SWITCH UP] dpid=%s connected", datapath.id)

        # table-miss: send to controller (no buffer)
        self.add_flow(datapath, 0, parser.OFPMatch(),
                      [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)])

        self.add_flow(
            datapath, 100,
            parser.OFPMatch(eth_type=0x0806),
            [
                parser.OFPActionOutput(ofproto.OFPP_FLOOD),
                parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER),
            ]
        )

        # When all 4 switches are up, apply baseline once
        if not self._baseline_done and len(self.dp_map) >= 4:
            self._break_all_links()
            self._baseline_done = True

    # -------- PacketIn handler --------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        reason = msg.reason
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        arp = pkt.get_protocol(arp_pkt.arp)
        if arp:
            # ARP has no IPv4 header, so use spa/tpa
            src_ip = arp.src_ip
            dst_ip = arp.dst_ip
            # only run policy for host-host pairs you care about
            src_node = self._ip2node.get(src_ip)
            dst_node = self._ip2node.get(dst_ip)
            if src_node and dst_node:
                switches = self._shortest_path_switches(src_node, dst_node)
                if switches is not None:
                    self.logger.info("SWs(ARP) - %s", ",".join(switches) if switches else "(none)")
                    letters = self._switches_to_link_names(switches)
                    self.logger.info("Link names(ARP) - %s", ",".join(letters) if letters else "(none)")
                    self._apply_link_policy(letters)
                # Handle only controller-processed packets


        # Parse IPs (IPv4 first, then IPv6)
        ip4 = pkt.get_protocol(ipv4_pkt.ipv4)
        if ip4:
            src_ip, dst_ip = ip4.src, ip4.dst
        else:
            ip6 = pkt.get_protocol(ipv6_pkt.ipv6)
            if ip6:
                src_ip, dst_ip = ip6.src, ip6.dst
            else:
                src_ip = dst_ip = None
        

        # -------- Learning switch fallback --------
        dpid = datapath.id
        dst = eth.dst
        src = eth.src

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions_flow = self._mirror_actions(parser, ofproto, out_port)
        actions_po = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions_flow, msg.buffer_id, idle_timeout=3)
                return
            else:
                self.add_flow(datapath, 1, match, actions_flow, idle_timeout=3)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions_po, data=data)
        datapath.send_msg(out)

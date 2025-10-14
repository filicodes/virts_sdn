
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

import json
import urllib.request
from ryu.lib import hub
import os, subprocess
import time

DROP_PRIO = 500

class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self._broken_letters = set()  # tracks which link letters are currently broken
        self._topology_ready = False     # set True after all switches are connected once
        self._policy_set_once = False    # ensure we only apply initial policy once
        here = os.path.dirname(os.path.abspath(__file__))
        self.dijkstra_script = os.path.normpath(os.path.join(here, "..", "algorithm", "virts_dijkstra.py"))

        self._printed_routes = set()

        self.mac_to_port = {}
        # registry of connected datapaths: dpid -> datapath object
        self.dp_map = {}
        self._broke_A = False
        

        # Testing delays - remove later
        self.delay_A = 5
        self.delay_B = 10
        self.delay_C = 15
        self.delay_D = 5
        self.delay_E = 10
        self.delay_F = 20

    # -------- Utility: build mirrored actions for installed flows --------
    def _mirror_actions(self, parser, ofproto, out_port):
        return [
            parser.OFPActionOutput(out_port),                         # normal forwarding
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,           # copy to controller
                                   ofproto.OFPCML_NO_BUFFER)
        ]

    # -------- Utility: add flow (supports idle_timeout) --------
    def add_flow(self, datapath, priority, match, actions,
                 buffer_id=None, idle_timeout=0):
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
    def _drop_inport(self, dp, in_port, priority=DROP_PRIO, cookie=0xA11A11A11):
        """Install a high-priority drop rule matching traffic arriving on in_port."""
        p = dp.ofproto_parser
        self.add_flow(dp, priority=priority, match=p.OFPMatch(in_port=in_port), actions=[])

    def _del_inport_drop(self, dp, in_port, priority=DROP_PRIO):
        """Delete previously installed drop rule on in_port (same priority)."""
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
        """Restore a broken link"""
        dp = self.dp_map.get(dpid)
        if not dp:
            self.logger.warning("DPID is not connected, Cannot restore the link - ", dpid, port)
            return
        self._del_inport_drop(dp, port)
    
    # Rules for restoring each link

    def _restore_link_A(self):
        dp1, dp2, dp3, dp4 = self.dp_map.get(1), self.dp_map.get(2), self.dp_map.get(3), self.dp_map.get(4)
        self._del_inport_drop(dp1, 2)
        self._del_inport_drop(dp2, 2)

    def _restore_link_B(self):
        dp1, dp2, dp3, dp4 = self.dp_map.get(1), self.dp_map.get(2), self.dp_map.get(3), self.dp_map.get(4)
        self._del_inport_drop(dp1, 3)
        self._del_inport_drop(dp3, 3)

    def _restore_link_C(self):
        dp1, dp2, dp3, dp4 = self.dp_map.get(1), self.dp_map.get(2), self.dp_map.get(3), self.dp_map.get(4)
        self._del_inport_drop(dp3, 2)
        self._del_inport_drop(dp4, 2)

    def _restore_link_D(self):
        dp1, dp2, dp3, dp4 = self.dp_map.get(1), self.dp_map.get(2), self.dp_map.get(3), self.dp_map.get(4)
        self._del_inport_drop(dp2, 3)
        self._del_inport_drop(dp4, 3)
    
    def _restore_link_E(self):
        dp1, dp2, dp3, dp4 = self.dp_map.get(1), self.dp_map.get(2), self.dp_map.get(3), self.dp_map.get(4)
        self._del_inport_drop(dp2, 4)
        self._del_inport_drop(dp3, 4)
    
    def _restore_link_F(self):
        dp1, dp2, dp3, dp4 = self.dp_map.get(1), self.dp_map.get(2), self.dp_map.get(3), self.dp_map.get(4)
        self._del_inport_drop(dp1, 5)
        self._del_inport_drop(dp4, 5)

    # All link restore
    def _restore_all_links(self):
        self._restore_link_A()
        self._restore_link_B()
        self._restore_link_C()
        self._restore_link_D()
        self._restore_link_E()
        self._restore_link_F()
        
    # Rules for breaking each link
    
    def break_link_A(self):
        dp1, dp2, dp3, dp4 = self.dp_map.get(1), self.dp_map.get(2), self.dp_map.get(3), self.dp_map.get(4)
        

        # Break Link A
        self._drop_inport(dp1, 2)
        self._drop_inport(dp2, 2)
    
    def break_link_B(self):
        dp1, dp2, dp3, dp4 = self.dp_map.get(1), self.dp_map.get(2), self.dp_map.get(3), self.dp_map.get(4)
        

        # Break Link B
        self._drop_inport(dp1, 3)
        self._drop_inport(dp3, 3)
    
    def break_link_C(self):
        dp1, dp2, dp3, dp4 = self.dp_map.get(1), self.dp_map.get(2), self.dp_map.get(3), self.dp_map.get(4)
        

        # Break Link C
        self._drop_inport(dp3, 2)
        self._drop_inport(dp4, 2)

    def break_link_D(self):
        dp1, dp2, dp3, dp4 = self.dp_map.get(1), self.dp_map.get(2), self.dp_map.get(3), self.dp_map.get(4)
        

        # Break Link D
        self._drop_inport(dp2, 3)
        self._drop_inport(dp4, 3)
    
    def break_link_E(self):
        dp1, dp2, dp3, dp4 = self.dp_map.get(1), self.dp_map.get(2), self.dp_map.get(3), self.dp_map.get(4)
        

        # Break Link E
        self._drop_inport(dp2, 4)
        self._drop_inport(dp3, 4)

    def break_link_F(self):
        dp1, dp2, dp3, dp4 = self.dp_map.get(1), self.dp_map.get(2), self.dp_map.get(3), self.dp_map.get(4)
        

        # Break Link F
        self._drop_inport(dp1, 5)
        self._drop_inport(dp4, 5)
    
    def _break_all_links(self):
        # self.break_link_A()
        self.break_link_B()
        # self.break_link_C()
        # self.break_link_D()
        self.break_link_E()
        self.break_link_F()
        self._broken_letters |= {"B","E","F"}

    # Functions to autorun djikstras code
    def _run_path(self, src_node: str, dst_node: str):
        """Run Dijkstra synchronously and return its full stdout as a string."""
        try:
            out = subprocess.check_output(
                ["python3", self.dijkstra_script, src_node, dst_node],
                stderr=subprocess.STDOUT,
                timeout=10,
            ).decode(errors="ignore").strip()
            self.logger.info("[Dijkstra] %s", out)
            return out
        except subprocess.CalledProcessError as e:
            self.logger.error("[Dijkstra] rc=%s: %s", e.returncode, e.output.decode(errors="ignore"))
        except Exception as e:
            self.logger.error("[Dijkstra] error: %r", e)
        return None
        

    def _run_dijkstra_and_log(self, src_node: str, dst_node: str):
        """
        Call: python3 sdn/ai/nx.py <src_node> <dst_node>
        and log the stdout.
        """
        
        try:
            out = subprocess.check_output(
                ["python3", self.dijkstra_script, src_node, dst_node],
                stderr=subprocess.STDOUT,
                timeout=10,
            ).decode(errors="ignore").strip()
            # Print to Ryu logs
            self.logger.warning("[Dijkstra] %s", out)
            return out
        except subprocess.CalledProcessError as e:
            self.logger.error("[Dijkstra] failed (rc=%s): %s", e.returncode, e.output.decode(errors="ignore"))
        except Exception as e:
            self.logger.error("[Dijkstra] error: %r", e)
            return None
    
    def _shortest_path_switches(self, src_node: str, dst_node: str) -> list[str] | None:
        """
        Runs Dijkstra and returns ['swX','swY', ...] from the 'nodes:' line.
        Returns None if not found.
        """
        out = self._run_path(src_node, dst_node)  # make sure this is synchronous
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
        """
        Given ['sw1','sw3','sw4'] return ['B','C'] by looking up each adjacent pair.
        Works for any length >= 2. Returns [] if none matched.
        """
        self._ensure_names_index()
        names = []
        sw_lc = [s.strip().lower() for s in switches if s]
        for a, b in zip(sw_lc, sw_lc[1:]):
            names.append(self._pair_to_name.get((a, b), None))
        # filter out None (in case a pair isn't present in names.json)
        return [n for n in names if n]
    
    # Call functions dynamically based on letters
    def _call_link_fn(self, prefix: str, letter: str):
        """
        Call break_link_{letter} or _restore_link_{letter} dynamically.
        prefix: 'break' or '_restore'
        """
        fn_name = f"{prefix}_link_{letter}"
        fn = getattr(self, fn_name, None)
        if callable(fn):
            fn()
        else:
            self.logger.error("Missing method: %s", fn_name)
    
    # Track and apply policy to restore and break links by calling relevant function
    def _apply_link_policy(self, keep_letters):
        """
        keep_letters: iterable of link letters to KEEP (e.g., ['A','E']).
        Breaks all other links, restores the kept ones if needed.
        """
        ALL = {'A','B','C','D','E','F'}
        keep = set(keep_letters or [])
        to_break = ALL - keep
        to_restore = keep

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

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # store datapath for later cross-programming
        self.dp_map[datapath.id] = datapath
        self.logger.info("[SWITCH UP] dpid=%s connected", datapath.id)

        # table-miss: send to controller (no buffer)
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
            

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
        
        

        # Parse IPs (IPv4 first, then IPv6)
        ip4 = pkt.get_protocol(ipv4_pkt.ipv4)
        if ip4:
            src_ip, dst_ip = ip4.src, ip4.dst
            # self.logger.debug("PktIn reason=%s IPv4 %s -> %s", reason, src_ip, dst_ip)

            
        else:
            ip6 = pkt.get_protocol(ipv6_pkt.ipv6)
            if ip6:
                src_ip, dst_ip = ip6.src, ip6.dst
            else:
                src_ip = dst_ip = None
        
                self._broke_A = False

        if reason != ofproto.OFPR_NO_MATCH:
            if src_ip and dst_ip:
                if ((src_ip == '10.0.0.1' and dst_ip == '10.0.0.2') or (src_ip == '10.0.0.2' and dst_ip == '10.0.0.1')):
                    # Run dijk
                    switches = self._shortest_path_switches("pc1", "pc2")
                    if switches is None:
                        self.logger.warning("No valid Dijkstra output for pc1<->pc2")
                    else:
                        # Log switches
                        self.logger.info("SWs - %s", ",".join(switches) if switches else "(none)")
                        # Map to letters
                        letters = self._switches_to_link_names(switches)  # e.g., ['B','C']
                        self.logger.info("Link names - %s", ",".join(letters) if letters else "(none)")

                        # Link breaking logic
                        self._apply_link_policy(letters)



                elif ((src_ip == '10.0.0.1' and dst_ip == '10.0.0.3') or (src_ip == '10.0.0.3' and dst_ip == '10.0.0.1')):
                    pass
                elif ((src_ip == '10.0.0.1' and dst_ip == '10.0.0.4') or (src_ip == '10.0.0.4' and dst_ip == '10.0.0.1')):
                    pass
                elif ((src_ip == '10.0.0.1' and dst_ip == '10.0.0.5') or (src_ip == '10.0.0.5' and dst_ip == '10.0.0.1')):
                    pass
                elif ((src_ip == '10.0.0.1' and dst_ip == '10.0.0.6') or (src_ip == '10.0.0.6' and dst_ip == '10.0.0.1')):
                    pass
                elif ((src_ip == '10.0.0.2' and dst_ip == '10.0.0.3') or (src_ip == '10.0.0.3' and dst_ip == '10.0.0.2')):
                    pass
                elif ((src_ip == '10.0.0.2' and dst_ip == '10.0.0.4') or (src_ip == '10.0.0.4' and dst_ip == '10.0.0.2')):
                    pass
                elif ((src_ip == '10.0.0.2' and dst_ip == '10.0.0.5') or (src_ip == '10.0.0.5' and dst_ip == '10.0.0.2')):
                    pass
                elif ((src_ip == '10.0.0.2' and dst_ip == '10.0.0.6') or (src_ip == '10.0.0.6' and dst_ip == '10.0.0.2')):
                    pass
                elif ((src_ip == '10.0.0.3' and dst_ip == '10.0.0.4') or (src_ip == '10.0.0.4' and dst_ip == '10.0.0.3')):
                    pass
                elif ((src_ip == '10.0.0.3' and dst_ip == '10.0.0.5') or (src_ip == '10.0.0.5' and dst_ip == '10.0.0.3')):
                    pass
                elif ((src_ip == '10.0.0.3' and dst_ip == '10.0.0.6') or (src_ip == '10.0.0.6' and dst_ip == '10.0.0.3')):
                    pass
                elif ((src_ip == '10.0.0.4' and dst_ip == '10.0.0.5') or (src_ip == '10.0.0.5' and dst_ip == '10.0.0.4')):
                    pass
                elif ((src_ip == '10.0.0.4' and dst_ip == '10.0.0.6') or (src_ip == '10.0.0.6' and dst_ip == '10.0.0.4')):
                    pass
                elif ((src_ip == '10.0.0.5' and dst_ip == '10.0.0.6') or (src_ip == '10.0.0.6' and dst_ip == '10.0.0.5')):
                    pass
                else:
                    pass
            return

                    # take djistra out and write function here - tomorrow
    




        # -------- only NO_MATCH below: do learning + PacketOut + (optional) flow install --------
        dpid = datapath.id
        dst = eth.dst
        src = eth.src

        self.mac_to_port.setdefault(dpid, {})
        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        # For installed flows, mirror; for this immediate PacketOut, DO NOT mirror.
        actions_flow = self._mirror_actions(parser, ofproto, out_port)
        actions_po = [parser.OFPActionOutput(out_port)]

        # install a short-lived learned flow (so mirroring doesn't persist forever)
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

# VIRTS SDN Controller & Topology

A Software-Defined Networking (SDN) test environment built with **Ryu**, **Mininet-WiFi**, and a custom Dijkstra-based path optimization algorithm.  
This project simulates dynamic link management, where the controller calculates the optimal switch path between hosts and automatically breaks or restores links to reflect the best route.

---

## 🧩 Project Structure

virts_sdn/
├── controller/
│ └── virts_controller.py # Ryu app: link control logic + Dijkstra integration
├── topology/
│ ├── virts_network.py # Mininet-WiFi topology definition
│ └── names.json # Link-to-name mapping (A–F)
├── algorithm/
│ └── virts_dijkstra.py # Dijkstra path calculation script
└── autorun.sh # Auto-launcher for Ryu + Mininet


---

## ⚙️ Features

- **Dynamic link control:** Ryu controller breaks/restores inter-switch links based on Dijkstra output.  
- **Dijkstra pathfinding:** Finds shortest path between communicating hosts.  
- **Link labeling:** Uses `names.json` to map switch pairs (e.g., sw1-sw3 → Link B).  
- **Mininet-WiFi topology:** Custom 4-switch, 6-host network with weighted links.  
- **Auto-run script:** Launches controller and topology in separate terminals automatically.  

---

## 🚀 Quick Start

### 1. Create & activate the virtual environment
```bash
python3 -m venv ~/ryu-venv
source ~/ryu-venv/bin/activate

2. Install dependencies

pip install ryu networkx mininet-wifi

3. Run everything automatically

bash autorun.sh

This will:

    Start the Ryu controller in one terminal.

    Wait 3 seconds.

    Run mn -c cleanup and launch the Mininet-WiFi topology in another terminal.

🧠 How It Works

    When a packet or ARP is detected, the controller:

        Extracts source/destination IPs.

        Calls the external Dijkstra algorithm (virts_dijkstra.py).

        Parses the path and maps adjacent switches to link letters.

        Restores active links in the best path and breaks all others.

    Dijkstra mathematically minimizes total link delay:
    δ(s,t)=min⁡p∈P(s,t)∑(u,v)∈pw(u,v)
    δ(s,t)=p∈P(s,t)min​(u,v)∈p∑​w(u,v)

    Example:

    pc1 → sw1 → sw3 → pc2
    Total weight = 5 ms

    Resulting path → Link B.

🧾 Example Output

[Dijkstra] nodes: pc1,sw1,sw3,pc2 (total: 5 ms)
SWs - sw1,sw3
Link names - B
Restored link B
Broke links: A,C,D,E,F

🧑‍💻 Useful Commands
Command	Description
sudo mn -c	Clean up previous Mininet state
ryu-manager virts_sdn/controller/virts_controller.py	Run controller manually
sudo python3 virts_sdn/topology/virts_network.py	Start topology manually
h1 ping h2	Ping between hosts to trigger Dijkstra
📊 Topology Overview

  pc1      pc2      pc3
   |        |        |
  sw1------sw2------sw3------sw4
   |        |        |
  pc4      pc5      pc6

Link labels (A–F) are defined in names.json and correspond to each inter-switch connection.
🧩 Requirements

    Python: ≥ 3.8

    Ryu Framework: ≥ 4.34

    Mininet-WiFi: latest build

    NetworkX: ≥ 3.0

    Ubuntu: recommended (tested on 22.04)

🧠 Notes

    Run the script inside the virtual environment (ryu-venv).

    You may need sudo privileges for Mininet.

    If visualization is needed, install matplotlib and use:

    from mininet_wifi.net import Mininet_wifi
    net.plotGraph(max_x=100, max_y=100)

    before net.start() in your topology script.

🧩 License

MIT License © 2025 Nimesha Nirmal Herath

💬 Author
Nimesha Herath
Master of Information Technology (Cybersecurity)
University of South Australia
# SAS EEW Group 1

## Getting Started

### 1. Install `uv`
`uv` is recommended for handling the Python environment.
- **How to install:** Go to [astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) and follow the instructions for your operating system.
- Restart your Terminal or IDE after the installation finishes.

### 2. Clone the project
To get the project onto your computer:
```bash
git clone https://github.com/chenneman/sas-eew-group-1.git
cd sas-eew-group-1
```

### 3. Get a Gurobi license
This project uses Gurobi to solve the routing optimization. It is recommended to get an academic license to avoid free-tier limits.
- Go to [Gurobi](https://portal.gurobi.com/iam/licenses/request/) and generate a WLS license. 
- Save the `gurobi.lic` file in the project root and create a `.env` file containing: `GRB_LICENSE_FILE=gurobi.lic`.

### 4. Set Up & Run
Once the project is open:
1. Open a **terminal** inside the directory.
2. **Install dependencies:**
   ```bash
   uv sync
   ```
3. **Run simulation:**
   ```bash
   uv run python main.py
   ```

### 5. Configuration & Results

- **Config:** Modify simulation parameters in `src/config.py`. Two important parameters are:
   - `ANIMATE = True | False` if set to `True`, a UI shows the physical movement of the AGVs and live statistics. If only numerical results are required, set to `False` for faster processing.
   - `INNOVATION_ENABLED = True | False` if set to `True`, the system uses multi-stop picking, else it assigns one order per AGV.
- **Logs:** Simulation results and event logs are saved in the `logs` directory. 

---

## Architecture & Directory Structure

This project uses a Domain-Driven Design approach to clearly separate the simulation's active components from the data they process and the environment they operate in.

- `scripts`: Scripts for data processing and visualization.
- `main.py`: The entry point that initializes and runs the simulation.
- `src/config.py`: Global configuration and simulation parameters.
- `src/components/`: **Active Entities.** These inherit from `salabim.Component`, consume time, and manage state (e.g., `AGV`, `Server`, `ControlSystem`).
- `src/entities/`: **Passive Entities.** Lightweight data containers (dataclasses) like `Order`, `Task`, or `Item`.
- `src/environment/`: **Static World.** Defines physical constraints and engines (e.g., `Warehouse`, `RoutingGraph`, `ServiceTimeGenerator`).
- `src/core/`: Central engine and metrics tracking.

---

## Development
### Branches
- `main` - The main branch. This is never edited directly.
- `Verifications,-validations-and-experiments` - A branch dedicated to the final testing of the model. 

Create a new branch for every new feature or bugfix, and open a pull request to merge it into `main`.

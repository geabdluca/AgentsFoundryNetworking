#!/usr/bin/env python3
"""
Azure AI Foundry Network Deployer

One-click deployment for hub-spoke network with AI Foundry.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# Constants
SCRIPT_DIR = Path(__file__).parent.resolve()
STATE_FILE = SCRIPT_DIR / ".deployment-state.json"
LOG_DIR = SCRIPT_DIR / "logs"
HUB_SPOKE_PATH = SCRIPT_DIR / "hub-spoke-network" / "code"
BYO_VNET_PATH = SCRIPT_DIR / "byo-vnet" / "code"
FOUNDRY_APIM_PATH = SCRIPT_DIR / "foundry-apim" / "code"
VPN_CLIENT_PATH = SCRIPT_DIR / "VpnClient"
TOTAL_STEPS = 5
MIN_TERRAFORM_VERSION = "1.10.0"

# Required Azure Resource Providers for AI Foundry with Standard Agents (VNet injection)
REQUIRED_RESOURCE_PROVIDERS = [
    "Microsoft.KeyVault",
    "Microsoft.CognitiveServices",
    "Microsoft.Storage",
    "Microsoft.Search",
    "Microsoft.Network",
    "Microsoft.App",
    "Microsoft.ContainerService",
]

# Resolve PowerShell path to avoid PATH resolution issues
POWERSHELL_PATH = shutil.which("powershell") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def _remove_readonly(func, path, _):
    """Error handler for shutil.rmtree to handle read-only files on Windows."""
    os.chmod(path, 0o777)
    func(path)


class Colors:
    """ANSI color codes for terminal output."""
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GRAY = "\033[90m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class Logger:
    """Handles logging to file and console."""
    
    def __init__(self):
        self.log_file = None
        self.buffer = []  # Buffer for prereq logs
        self.buffering = False  # Whether to buffer instead of write
    
    def initialize(self, operation="deploy"):
        LOG_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        self.log_file = LOG_DIR / f"{operation}-{timestamp}.log"
        self.buffering = False
        self.buffer = []
        self.log(f"=== {operation.title()} Started ===")
        return self.log_file
    
    def start_buffering(self, operation="prereq-check"):
        """Start buffering logs instead of writing to file."""
        self.buffering = True
        self.buffer = []
        LOG_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        self.log_file = LOG_DIR / f"{operation}-{timestamp}.log"
        self.log(f"=== {operation.title()} Started ===")
    
    def flush_buffer(self):
        """Write buffered logs to file (call when prereqs fail)."""
        if self.buffer and self.log_file:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    for entry in self.buffer:
                        f.write(entry + "\n")
            except OSError:
                pass
        self.buffer = []
        self.buffering = False
    
    def discard_buffer(self):
        """Discard buffered logs (call when prereqs pass)."""
        self.buffer = []
        self.buffering = False
        self.log_file = None
    
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        if self.buffering:
            self.buffer.append(log_entry)
        elif self.log_file:
            _append_to_log(self.log_file, log_entry + "\n")
    
    def show_tail(self, lines=20):
        if self.log_file and self.log_file.exists():
            print(f"\n{Colors.YELLOW}--- Last {lines} lines of log ---{Colors.RESET}")
            with open(self.log_file, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
                for line in all_lines[-lines:]:
                    print(f"{Colors.GRAY}{line.rstrip()}{Colors.RESET}")
            print(f"{Colors.YELLOW}--- Full log: {self.log_file} ---{Colors.RESET}\n")


logger = Logger()


def _append_to_log(log_file, content):
    """Append content to a log file, silently ignoring permission/IO errors."""
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(content)
    except OSError:
        pass  # Log file locked (e.g. open in editor) — never crash the deployer


def print_banner():
    """Display the welcome banner."""
    print(f"""
{Colors.CYAN}================================================================
         Azure AI Foundry Network Deployer v1.0                 
                                                                
  Deploys hub-spoke network with VPN, DNS, and AI Foundry      
================================================================{Colors.RESET}
""")


def print_step(step_num, message):
    """Print a step header."""
    print(f"\n{Colors.CYAN}[Step {step_num}/{TOTAL_STEPS}] {message}{Colors.RESET}")
    logger.log(f"[Step {step_num}/{TOTAL_STEPS}] {message}")


def print_result(success, message):
    """Print a step result."""
    if success:
        print(f"  {Colors.GREEN}[OK] {message}{Colors.RESET}")
        logger.log(f"SUCCESS: {message}", "SUCCESS")
    else:
        print(f"  {Colors.RED}[FAIL] {message}{Colors.RESET}")
        logger.log(f"FAILED: {message}", "ERROR")


def print_completion(log_path, state):
    """Display completion banner with resource links."""
    # Get resource info
    byo_info = get_byo_resource_info(state)
    foundry_name = get_terraform_output(BYO_VNET_PATH, "ai_foundry_name")
    project_name = get_terraform_output(BYO_VNET_PATH, "ai_foundry_project_name")
    vpn_name = get_terraform_output(HUB_SPOKE_PATH, "vpn_gateway_name")
    hub_info = get_hub_spoke_resource_info(state)
    
    # Get tenant ID from Azure CLI
    tenant_id = ""
    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "tenantId", "-o", "tsv"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            tenant_id = result.stdout.strip()
    except Exception:
        pass
    
    print(f"\n{Colors.GREEN}================================================================")
    print(f"  DEPLOYMENT COMPLETE")
    print(f"================================================================{Colors.RESET}")
    
    print(f"\n  {Colors.CYAN}Resources Created:{Colors.RESET}")
    
    # Hub-Spoke RG
    if hub_info["resource_group"]:
        hub_rg_url = f"https://portal.azure.com/#@/resource/subscriptions/{state['subscription_id']}/resourceGroups/{hub_info['resource_group']}/overview"
        print(f"  Hub-Spoke RG: {hub_info['resource_group']}")
        print(f"    {Colors.GRAY}{hub_rg_url}{Colors.RESET}")
    
    # AI Foundry RG
    if byo_info["resource_group"] and byo_info["resource_group"] != "rg-aifoundry-resources":
        foundry_rg_url = f"https://portal.azure.com/#@/resource/subscriptions/{state['subscription_id']}/resourceGroups/{byo_info['resource_group']}/overview"
        print(f"  AI Foundry RG: {byo_info['resource_group']}")
        print(f"    {Colors.GRAY}{foundry_rg_url}{Colors.RESET}")
    
    # AI Foundry Portal link
    if foundry_name and project_name and tenant_id:
        foundry_url = f"https://ai.azure.com/foundryProject/overview?wsid=/subscriptions/{state['subscription_id']}/resourceGroups/{byo_info['resource_group']}/providers/Microsoft.CognitiveServices/accounts/{foundry_name}/projects/{project_name}&tid={tenant_id}"
        print(f"\n  {Colors.CYAN}AI Foundry Project:{Colors.RESET} {project_name}")
        print(f"    {Colors.GRAY}{foundry_url}{Colors.RESET}")
    
    print(f"\n  {Colors.CYAN}Next Steps:{Colors.RESET}")
    if vpn_name:
        print(f"  1. Connect to VPN '{vpn_name}' using Azure VPN Client")
    else:
        print(f"  1. Connect to VPN using Azure VPN Client")
    print(f"  2. Access AI Foundry: https://ai.azure.com")
    
    print(f"\n  {Colors.GRAY}Log file: {log_path}{Colors.RESET}")
    print(f"{Colors.GREEN}================================================================{Colors.RESET}\n")


def confirm(prompt, default=True):
    """Ask for user confirmation."""
    default_text = "[Y/n]" if default else "[y/N]"
    response = input(f"{Colors.YELLOW}{prompt} {default_text} {Colors.RESET}").strip()
    if not response:
        return default
    return response.lower().startswith("y")


def prompt_input(prompt, example="", default=""):
    """Prompt for user input."""
    prompt_text = f"  -> {prompt}"
    if example:
        prompt_text += f" (e.g. {example})"
    if default:
        prompt_text += f" [{default}]"
    prompt_text += ": "
    
    response = input(f"{Colors.YELLOW}{prompt_text}{Colors.RESET}").strip()
    if not response and default:
        return default
    return response


# State Management
def load_state():
    """Load deployment state from file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_state(state):
    """Save deployment state to file."""
    # On Windows, remove hidden attribute before writing (if file exists)
    if sys.platform == "win32" and STATE_FILE.exists():
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(STATE_FILE), 0)  # Remove hidden
    
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    
    # Make hidden on Windows after writing
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(STATE_FILE), 2)  # FILE_ATTRIBUTE_HIDDEN


def create_state(subscription_id, location, deploy_firewall):
    """Create a new deployment state."""
    return {
        "version": "1.0",
        "subscription_id": subscription_id,
        "location": location,
        "deploy_firewall": deploy_firewall,
        "created_at": datetime.now().isoformat(),
        "rp_registered": False,  # Track if resource providers have been verified/registered
        "foundry_type": None,  # "byo" or "apim" - set when user selects at Step 5
        "resources": {
            "hub_spoke_rg": None,
            "vpn_gateway_name": None,
            "byo_vnet_rg": None,
            "ai_foundry_name": None,
            "ai_foundry_project_name": None,
        },
        "steps": {
            "hub_spoke": {"status": "pending", "timestamp": None},
            "dns_install": {"status": "pending", "timestamp": None},
            "cert_install": {"status": "pending", "timestamp": None},
            "vpn_client": {"status": "pending", "timestamp": None},
            "byo_vnet": {"status": "pending", "timestamp": None},
        }
    }


def update_step(state, step_name, status):
    """Update a step status in the state."""
    state["steps"][step_name]["status"] = status
    state["steps"][step_name]["timestamp"] = datetime.now().isoformat()
    save_state(state)
    return state


def count_completed(state):
    """Count completed steps."""
    return sum(1 for s in state["steps"].values() if s["status"] in ("completed", "skipped"))


def has_previous_deployment():
    """Check if there's a previous deployment."""
    state = load_state()
    if not state:
        return False
    return any(s["status"] == "completed" for s in state["steps"].values())


def has_resources_to_destroy():
    """Check if there are any resources that can be destroyed."""
    state = load_state()
    if not state:
        return False
    # Check if hub_spoke or byo_vnet are completed, failed, or in_progress (meaning resources may exist)
    hub_spoke_status = state["steps"].get("hub_spoke", {}).get("status", "pending")
    byo_vnet_status = state["steps"].get("byo_vnet", {}).get("status", "pending")
    return hub_spoke_status in ("completed", "failed", "in_progress") or byo_vnet_status in ("completed", "failed", "in_progress")


def get_foundry_tf_path(state):
    """Return the Terraform path for the deployed foundry type (BYO or APIM)."""
    if state.get("foundry_type") == "apim":
        return FOUNDRY_APIM_PATH
    return BYO_VNET_PATH


def get_foundry_label(state):
    """Return a human-readable label for the deployed foundry type."""
    if state.get("foundry_type") == "apim":
        return "AI Foundry + APIM"
    if state.get("foundry_type") == "none":
        return "Hub-Spoke only (no AI Foundry)"
    return "AI Foundry (BYO VNet)"


def has_terraform_state_files():
    """Check if any terraform state files exist."""
    hub_state = HUB_SPOKE_PATH / "terraform.tfstate"
    byo_state = BYO_VNET_PATH / "terraform.tfstate"
    apim_state = FOUNDRY_APIM_PATH / "terraform.tfstate"
    deployment_state = STATE_FILE
    return hub_state.exists() or byo_state.exists() or apim_state.exists() or deployment_state.exists()


def run_reset():
    """Delete all state files for a fresh start."""
    print(f"\n{Colors.RED}=== Reset - Fresh Start ==={Colors.RESET}")
    
    # Check for existing Azure resource groups first
    print(f"\n  {Colors.GRAY}Checking for existing Azure resource groups...{Colors.RESET}")
    existing_rgs = []
    try:
        # Get subscription from state or prompt
        state = load_state()
        subscription_id = state.get("subscription_id") if state else None
        
        if subscription_id:
            result = subprocess.run(
                f'az group list --subscription "{subscription_id}" --query "[?starts_with(name, \'rg-aifoundry-\')].name" -o tsv',
                capture_output=True, text=True, shell=True, timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                existing_rgs = [rg.strip() for rg in result.stdout.strip().split('\n') if rg.strip()]
    except Exception:
        pass
    
    if existing_rgs:
        print(f"\n  {Colors.RED}WARNING: Found existing Azure resource groups:{Colors.RESET}")
        for rg in existing_rgs:
            print(f"    {Colors.RED}- {rg}{Colors.RESET}")
        print(f"\n  {Colors.RED}These resources will cause deployment conflicts!{Colors.RESET}")
        print(f"  {Colors.YELLOW}Please delete them in Azure Portal or run Destroy first.{Colors.RESET}")
        
        if not confirm("Continue with Reset anyway?", default=False):
            print(f"\n{Colors.YELLOW}Reset cancelled. Delete Azure resources first.{Colors.RESET}")
            input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")
            return
    
    print(f"\n  {Colors.YELLOW}This will delete:{Colors.RESET}")
    
    files_to_delete = []

    # Check what exists
    hub_state = HUB_SPOKE_PATH / "terraform.tfstate"
    hub_backup = HUB_SPOKE_PATH / "terraform.tfstate.backup"
    hub_lock = HUB_SPOKE_PATH / ".terraform.lock.hcl"
    byo_state = BYO_VNET_PATH / "terraform.tfstate"
    byo_backup = BYO_VNET_PATH / "terraform.tfstate.backup"
    byo_lock = BYO_VNET_PATH / ".terraform.lock.hcl"
    apim_state = FOUNDRY_APIM_PATH / "terraform.tfstate"
    apim_backup = FOUNDRY_APIM_PATH / "terraform.tfstate.backup"
    apim_lock = FOUNDRY_APIM_PATH / ".terraform.lock.hcl"

    if hub_state.exists():
        files_to_delete.append(("Hub-Spoke terraform.tfstate", hub_state))
    if hub_backup.exists():
        files_to_delete.append(("Hub-Spoke terraform.tfstate.backup", hub_backup))
    if hub_lock.exists():
        files_to_delete.append(("Hub-Spoke .terraform.lock.hcl", hub_lock))
    if byo_state.exists():
        files_to_delete.append(("BYO VNet terraform.tfstate", byo_state))
    if byo_backup.exists():
        files_to_delete.append(("BYO VNet terraform.tfstate.backup", byo_backup))
    if byo_lock.exists():
        files_to_delete.append(("BYO VNet .terraform.lock.hcl", byo_lock))
    if apim_state.exists():
        files_to_delete.append(("Foundry+APIM terraform.tfstate", apim_state))
    if apim_backup.exists():
        files_to_delete.append(("Foundry+APIM terraform.tfstate.backup", apim_backup))
    if apim_lock.exists():
        files_to_delete.append(("Foundry+APIM .terraform.lock.hcl", apim_lock))
    if STATE_FILE.exists():
        files_to_delete.append(("Deployment state (.deployment-state.json)", STATE_FILE))
    
    if not files_to_delete:
        print(f"  {Colors.GRAY}No state files found.{Colors.RESET}")
        input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")
        return
    
    for name, _ in files_to_delete:
        print(f"    - {name}")
    
    print(f"\n  {Colors.RED}WARNING: This will NOT delete Azure resources!{Colors.RESET}")
    print(f"  {Colors.RED}If resources exist, delete them in Azure Portal first.{Colors.RESET}")
    
    if not confirm("Delete all state files?", default=False):
        print(f"\n{Colors.YELLOW}Reset cancelled.{Colors.RESET}")
        input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")
        return
    
    # Delete files
    deleted = []
    for name, path in files_to_delete:
        try:
            path.unlink()
            deleted.append(name)
        except Exception as e:
            print(f"  {Colors.RED}[FAIL] Could not delete {name}: {e}{Colors.RESET}")
    
    if deleted:
        print(f"\n  {Colors.GREEN}[OK] Deleted:{Colors.RESET}")
        for name in deleted:
            print(f"    - {name}")
    
    print(f"\n{Colors.GREEN}Reset complete! You can now start a fresh deployment.{Colors.RESET}")
    input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")


def run_reselect_foundry():
    """Allow the user to change their BYO vs APIM choice before Step 5 runs.
    Blocks if the previous choice created Azure resources (destroy first)."""
    print(f"\n{Colors.CYAN}=== Reselect Foundry Type ==={Colors.RESET}")

    state = load_state()
    if not state:
        print(f"\n  {Colors.YELLOW}No deployment state found. Start a deployment first.{Colors.RESET}")
        input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")
        return

    prev_type = state.get("foundry_type")
    prev_label = get_foundry_label(state) if prev_type else "(not yet selected)"
    print(f"\n  Current choice: {Colors.CYAN}{prev_label}{Colors.RESET}")

    print(f"\n  {Colors.CYAN}Choose your AI Foundry deployment option:{Colors.RESET}")
    print(f"    [1] AI Foundry (BYO VNet)  - Standard private network deployment (~20-30 min)")
    print(f"    [2] AI Foundry + APIM      - Adds API Management for controlled access (~45-60 min)")
    print(f"    [3] Hub-Spoke only         - Skip AI Foundry, use network infrastructure only")
    print(f"    [0] Cancel")

    while True:
        ft_choice = input(f"\n{Colors.YELLOW}  Select option [0/1/2/3]: {Colors.RESET}").strip()
        if ft_choice == "0":
            print(f"\n{Colors.YELLOW}Cancelled.{Colors.RESET}")
            input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")
            return
        elif ft_choice in ("1", "2", "3"):
            break
        else:
            print(f"  {Colors.RED}Please enter 0, 1, 2, or 3.{Colors.RESET}")

    new_type = "byo" if ft_choice == "1" else ("apim" if ft_choice == "2" else "none")

    # If switching, check the stale state path for existing Azure resources
    if prev_type and prev_type != new_type:
        stale_path = BYO_VNET_PATH if new_type == "apim" else FOUNDRY_APIM_PATH
        stale_state_file = stale_path / "terraform.tfstate"
        if stale_state_file.exists():
            has_resources = False
            try:
                with open(stale_state_file) as f:
                    tf_state_data = json.load(f)
                has_resources = bool(tf_state_data.get("resources"))
            except Exception:
                has_resources = True  # can't parse → assume resources exist
            if has_resources:
                print(f"\n  {Colors.RED}Cannot switch: the previous {prev_label} attempt created Azure resources.{Colors.RESET}")
                print(f"  {Colors.YELLOW}Use option [2] Destroy from the main menu to clean them up first.{Colors.RESET}")
                input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")
                return
            # Plan-only failure – safe to remove stale state
            for fname in ("terraform.tfstate", "terraform.tfstate.backup"):
                stale_file = stale_path / fname
                if stale_file.exists():
                    try:
                        stale_file.unlink()
                        print(f"  {Colors.GRAY}Removed stale state: {stale_file.name}{Colors.RESET}")
                    except Exception:
                        pass

    state["foundry_type"] = new_type
    # Reset step 5 so Deploy will re-run it with the new choice
    state["steps"]["byo_vnet"] = {"status": "pending", "timestamp": None}
    for key in ("byo_vnet_rg", "ai_foundry_name", "ai_foundry_project_name"):
        state["resources"][key] = None
    save_state(state)

    new_label = get_foundry_label(state)
    print(f"\n{Colors.GREEN}Foundry type set to: {new_label}{Colors.RESET}")
    print(f"  Run option [1] Deploy to continue.")
    input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")


# ============================================
# DESTROY FUNCTIONS
# ============================================

def run_terraform_destroy(working_dir, subscription_id, log_file):
    """Run terraform destroy in a directory."""
    original_dir = os.getcwd()
    os.chdir(working_dir)
    
    try:
        env = os.environ.copy()
        env["ARM_SUBSCRIPTION_ID"] = subscription_id
        
        # Ensure critical Windows system paths are present (required for Azure CLI credential chain)
        system_root = os.environ.get("SystemRoot", r"C:\WINDOWS")
        critical_paths = [
            os.path.join(system_root, "system32"),
            system_root,
        ]
        current_path = env.get("PATH", "")
        for critical_path in critical_paths:
            if critical_path.lower() not in current_path.lower():
                current_path = critical_path + ";" + current_path
        env["PATH"] = current_path
        
        # First run terraform init (needed if lock file was deleted)
        print(f"  {Colors.GRAY}Initializing Terraform...{Colors.RESET}")
        init_result = subprocess.run(
            ["terraform", "init", "-no-color", "-input=false"],
            capture_output=True, text=True, env=env, timeout=300
        )
        
        _append_to_log(log_file, f"terraform init (destroy): {init_result.stdout}\n{init_result.stderr}\n")
        
        if init_result.returncode != 0:
            return False, f"Terraform init failed: {init_result.stderr}"
        
        print(f"  {Colors.GRAY}Running terraform destroy...{Colors.RESET}")
        result = subprocess.run(
            ["terraform", "destroy", "-auto-approve", "-no-color"],
            capture_output=True, text=True, env=env, timeout=1800  # 30 min timeout
        )
        
        _append_to_log(log_file, result.stdout + result.stderr)
        
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Terraform destroy timed out after 30 minutes"
    except Exception as e:
        return False, str(e)
    finally:
        os.chdir(original_dir)


def delete_resource_group(rg_name, subscription_id, log_file):
    """Delete an Azure resource group."""
    print(f"  {Colors.GRAY}Checking if resource group {rg_name} exists...{Colors.RESET}")
    
    # Check if RG exists first
    check = subprocess.run(
        f'az group exists --name "{rg_name}" --subscription "{subscription_id}"',
        capture_output=True, text=True, shell=True
    )
    
    if check.stdout.strip().lower() == "false":
        print(f"  {Colors.GRAY}Resource group already deleted or doesn't exist{Colors.RESET}")
        return True, "Resource group already deleted"
    
    print(f"  {Colors.GRAY}Deleting resource group {rg_name}...{Colors.RESET}")
    
    result = subprocess.run(
        f'az group delete --name "{rg_name}" --subscription "{subscription_id}" --yes --no-wait',
        capture_output=True, text=True, shell=True
    )
    
    _append_to_log(log_file, f"az group delete: {result.stdout} {result.stderr}\n")
    
    if result.returncode != 0:
        return False, result.stderr
    
    # Wait for deletion to complete
    print(f"  {Colors.GRAY}Waiting for resource group deletion...{Colors.RESET}")
    for i in range(360):  # Wait up to 60 minutes (10s intervals)
        check = subprocess.run(
            f'az group exists --name "{rg_name}" --subscription "{subscription_id}"',
            capture_output=True, text=True, shell=True
        )
        if check.stdout.strip().lower() == "false":
            return True, "Resource group deleted"
        time.sleep(10)
        if i % 6 == 0:  # Every minute
            print(f"  {Colors.GRAY}  Still waiting... ({i*10}s){Colors.RESET}")
    
    return False, "Timeout waiting for resource group deletion"


def purge_cognitive_services(account_name, resource_group, location, subscription_id, log_file):
    """Purge a soft-deleted cognitive services account."""
    print(f"  {Colors.GRAY}Purging cognitive services account {account_name}...{Colors.RESET}")
    
    # Wait for account to appear in deleted list (can take up to 60 seconds)
    print(f"  {Colors.GRAY}Waiting for account to appear in deleted accounts list...{Colors.RESET}")
    account_found = False
    for attempt in range(12):  # Wait up to 2 minutes
        check_result = subprocess.run(
            f'az cognitiveservices account list-deleted --subscription "{subscription_id}" --query "[?name==\'{account_name}\'].name" -o tsv',
            capture_output=True, text=True, shell=True
        )
        
        if account_name in check_result.stdout:
            account_found = True
            break
        
        if attempt < 11:
            time.sleep(10)
            print(f"  {Colors.GRAY}  Still waiting... ({(attempt+1)*10}s){Colors.RESET}")
    
    if not account_found:
        _append_to_log(log_file, f"Account {account_name} not found in deleted accounts after waiting, skipping purge\n")
        print(f"  {Colors.YELLOW}Account not found in deleted accounts after 2 minutes{Colors.RESET}")
        return True, "Account not in deleted state, skipping purge"
    
    print(f"  {Colors.GRAY}Account found, purging...{Colors.RESET}")
    
    # Purge using az cognitiveservices account purge (requires original resource group name)
    result = subprocess.run(
        f'az cognitiveservices account purge --name "{account_name}" --resource-group "{resource_group}" --location "{location}" --subscription "{subscription_id}"',
        capture_output=True, text=True, shell=True
    )
    
    _append_to_log(log_file, f"az cognitiveservices account purge: {result.stdout} {result.stderr}\n")
    
    # Check if purge succeeded
    if result.returncode == 0:
        # Wait a moment and verify
        time.sleep(5)
        verify_result = subprocess.run(
            f'az cognitiveservices account list-deleted --subscription "{subscription_id}" --query "[?name==\'{account_name}\'].name" -o tsv',
            capture_output=True, text=True, shell=True
        )
        if account_name not in verify_result.stdout:
            return True, "Account purged successfully"
        else:
            return True, "Purge command succeeded (account may take time to disappear)"
    
    # Verify if account is actually gone (purge might have worked despite error)
    verify_result = subprocess.run(
        f'az cognitiveservices account list-deleted --subscription "{subscription_id}" --query "[?name==\'{account_name}\'].name" -o tsv',
        capture_output=True, text=True, shell=True
    )
    
    if account_name not in verify_result.stdout:
        return True, "Account purged (verified)"
    
    return False, result.stderr


def remove_terraform_state(working_dir, log_file):
    """Remove terraform state files from a directory (keeps .terraform for faster re-init)."""
    state_files = [
        working_dir / "terraform.tfstate",
        working_dir / "terraform.tfstate.backup",
        working_dir / ".terraform.lock.hcl",
    ]
    
    removed = []
    for sf in state_files:
        if sf.exists():
            try:
                sf.unlink()
                removed.append(sf.name)
            except Exception as e:
                logger.log(f"Failed to remove {sf}: {e}", "WARNING")
    
    # Also remove any backup files
    for backup in working_dir.glob("terraform.tfstate.*.backup"):
        try:
            backup.unlink()
            removed.append(backup.name)
        except Exception:
            pass
    
    _append_to_log(log_file, f"Removed terraform state files: {removed}\n")
    
    return removed


def remove_vpn_client_files(log_file):
    """Remove downloaded VPN client files."""
    removed = []
    
    # Remove VpnClient directory in script root (legacy location)
    vpn_dir_root = SCRIPT_DIR / "VpnClient"
    if vpn_dir_root.exists():
        try:
            shutil.rmtree(vpn_dir_root, onerror=_remove_readonly)
            removed.append("VpnClient/")
        except Exception as e:
            logger.log(f"Failed to remove VpnClient: {e}", "WARNING")
    
    # Remove VpnClient directory under hub-spoke-network (current location)
    vpn_dir_hub = SCRIPT_DIR / "hub-spoke-network" / "VpnClient"
    if vpn_dir_hub.exists():
        try:
            shutil.rmtree(vpn_dir_hub, onerror=_remove_readonly)
            removed.append("hub-spoke-network/VpnClient/")
        except Exception as e:
            logger.log(f"Failed to remove hub-spoke-network/VpnClient: {e}", "WARNING")
    
    # Remove any downloaded zip files from both locations
    for search_dir in [SCRIPT_DIR, SCRIPT_DIR / "hub-spoke-network"]:
        for zf in search_dir.glob("vpnclient*.zip"):
            try:
                zf.unlink()
                removed.append(str(zf.relative_to(SCRIPT_DIR)))
            except Exception:
                pass
        for zf in search_dir.glob("VpnClient.zip"):
            try:
                zf.unlink()
                removed.append(str(zf.relative_to(SCRIPT_DIR)))
            except Exception:
                pass
    
    _append_to_log(log_file, f"Removed VPN client files: {removed}\n")
    
    return removed


def remove_vpn_connection_profile(log_file):
    """Remove VPN connection profile from Windows."""
    logger.log("Removing VPN connection profiles...")
    removed = []
    
    # Method 1: Use Get-VpnConnection for standard VPN connections
    # ONLY match connections created by this launcher:
    # - vnet-hub-* (PowerShell VPN option uses VNet name from VpnSettings.xml)
    # - Azure-AI-Foundry-VPN (fallback name if VnetName is missing)
    try:
        cmd = [POWERSHELL_PATH, '-NoProfile', '-Command', 
               'Get-VpnConnection | Where-Object { $_.Name -like "vnet-hub-*" -or $_.Name -eq "Azure-AI-Foundry-VPN" } | Select-Object -ExpandProperty Name']
        logger.log(f"  Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        logger.log(f"  Exit code: {result.returncode}")
        
        if result.returncode == 0 and result.stdout.strip():
            for vpn_name in result.stdout.strip().split('\n'):
                vpn_name = vpn_name.strip()
                if vpn_name:
                    print(f"  {Colors.GRAY}Removing VPN connection: {vpn_name}{Colors.RESET}")
                    logger.log(f"  Removing VPN connection: {vpn_name}")
                    try:
                        del_result = subprocess.run(
                            [POWERSHELL_PATH, '-NoProfile', '-Command',
                             f'Remove-VpnConnection -Name "{vpn_name}" -Force -ErrorAction SilentlyContinue'],
                            capture_output=True, text=True
                        )
                        if del_result.returncode == 0:
                            removed.append(vpn_name)
                            logger.log(f"    Removed successfully")
                    except Exception as e:
                        logger.log(f"    ERROR removing: {e}", "ERROR")
    except FileNotFoundError as e:
        logger.log(f"  ERROR: PowerShell not found - {e}", "ERROR")
    except Exception as e:
        logger.log(f"  ERROR: {type(e).__name__} - {e}", "ERROR")
    
    # Method 2: Also check phonebook files for vnet-hub-* entries that Get-VpnConnection might miss
    # Use rasphone -r to remove these entries
    try:
        pbk_path = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Network" / "Connections" / "Pbk"
        if pbk_path.exists():
            for pbk_file in pbk_path.rglob("*.pbk"):
                try:
                    content = pbk_file.read_text(encoding='utf-8', errors='ignore')
                    # Find vnet-hub-* entries in phonebook
                    import re
                    for match in re.finditer(r'^\[(vnet-hub-[^\]]+)\]', content, re.MULTILINE):
                        vpn_name = match.group(1)
                        if vpn_name not in removed:
                            print(f"  {Colors.GRAY}Removing VPN connection (phonebook): {vpn_name}{Colors.RESET}")
                            logger.log(f"  Removing VPN connection via rasphone: {vpn_name}")
                            try:
                                del_result = subprocess.run(
                                    ["rasphone", "-r", vpn_name],
                                    capture_output=True, text=True
                                )
                                if del_result.returncode == 0:
                                    removed.append(vpn_name)
                                    logger.log(f"    Removed successfully via rasphone")
                            except Exception as e:
                                logger.log(f"    ERROR removing via rasphone: {e}", "ERROR")
                except Exception as e:
                    logger.log(f"  ERROR reading phonebook {pbk_file}: {e}", "ERROR")
    except Exception as e:
        logger.log(f"  ERROR checking phonebook: {e}", "ERROR")
    
    _append_to_log(log_file, f"Removed VPN connections: {removed}\n")
    
    return removed


def get_terraform_output(tf_dir, output_name):
    """Get a single terraform output value by reading state file directly."""
    try:
        state_file = tf_dir / "terraform.tfstate"
        if not state_file.exists():
            return None
        
        with open(state_file, "r", encoding="utf-8") as f:
            tf_state = json.load(f)
        
        outputs = tf_state.get("outputs", {})
        if output_name in outputs:
            return outputs[output_name].get("value")
        return None
    except Exception:
        return None


def get_byo_resource_info(state):
    """Get foundry resource information (BYO VNet or APIM) by reading terraform state file."""
    info = {
        "resource_group": "rg-aifoundry-resources",  # Default
        "ai_foundry_name": None,
        "location": state.get("location", "westus")
    }

    # First check if saved in deployment state
    if state.get("resources", {}).get("byo_vnet_rg"):
        info["resource_group"] = state["resources"]["byo_vnet_rg"]
    if state.get("resources", {}).get("ai_foundry_name"):
        info["ai_foundry_name"] = state["resources"]["ai_foundry_name"]
        return info  # If we have saved state, use it

    # Fall back to terraform state file (check both BYO and APIM paths)
    tf_path = get_foundry_tf_path(state)
    try:
        state_file = tf_path / "terraform.tfstate"
        if not state_file.exists():
            return info

        with open(state_file, "r", encoding="utf-8") as f:
            tf_state = json.load(f)

        outputs = tf_state.get("outputs", {})

        if "ai_foundry_name" in outputs:
            info["ai_foundry_name"] = outputs["ai_foundry_name"].get("value")

        if "resource_group_name" in outputs:
            info["resource_group"] = outputs["resource_group_name"].get("value")
    except Exception:
        pass

    return info


def get_hub_spoke_resource_info(state):
    """Get Hub-Spoke resource information by reading terraform state file directly."""
    info = {
        "resource_group": None,
        "location": state.get("location", "westus")
    }
    
    # First check if saved in deployment state
    if state.get("resources", {}).get("hub_spoke_rg"):
        info["resource_group"] = state["resources"]["hub_spoke_rg"]
        return info
    
    # Fall back to terraform state file
    try:
        state_file = HUB_SPOKE_PATH / "terraform.tfstate"
        if not state_file.exists():
            return info
        
        with open(state_file, "r", encoding="utf-8") as f:
            tf_state = json.load(f)
        
        outputs = tf_state.get("outputs", {})
        
        if "resource_group_name" in outputs:
            info["resource_group"] = outputs["resource_group_name"].get("value")
    except Exception:
        pass
    
    return info


def delete_apim_instances(resource_group, subscription_id, log_file):
    """Find and delete all APIM instances in a resource group, waiting for full VNet de-injection.

    APIM in Internal VNet mode injects NICs into the spoke subnet. The RG cannot be
    deleted until those NICs are removed, which only happens after APIM is fully deleted.
    This must be done BEFORE issuing az group delete, otherwise the RG deletion either
    times out or hangs waiting for APIM VNet cleanup (30-45 min).
    """
    # List all APIM instances in the RG
    list_result = subprocess.run(
        f'az apim list --resource-group "{resource_group}" --subscription "{subscription_id}" --query "[].name" --output tsv',
        capture_output=True, text=True, shell=True
    )
    _append_to_log(log_file, f"az apim list: {list_result.stdout} {list_result.stderr}\n")

    apim_names = [n.strip() for n in list_result.stdout.strip().splitlines() if n.strip()]
    if not apim_names:
        print(f"  {Colors.GRAY}No APIM instances found in RG, skipping pre-deletion{Colors.RESET}")
        return True

    for apim_name in apim_names:
        print(f"  {Colors.YELLOW}Deleting APIM '{apim_name}' (VNet de-injection takes 30-45 min)...{Colors.RESET}")
        logger.log(f"Pre-deleting APIM {apim_name} to allow RG deletion")

        del_result = subprocess.run(
            f'az apim delete --name "{apim_name}" --resource-group "{resource_group}" --subscription "{subscription_id}" --yes',
            capture_output=True, text=True, shell=True
        )
        _append_to_log(log_file, f"az apim delete {apim_name}: {del_result.stdout} {del_result.stderr}\n")

        if del_result.returncode != 0:
            # Already gone or deletion kicked off — non-fatal, RG delete will handle it
            print(f"  {Colors.YELLOW}  APIM delete command returned non-zero (may already be deleting): {del_result.stderr[:200]}{Colors.RESET}")

        # Poll until APIM is gone (up to 60 min)
        print(f"  {Colors.GRAY}  Waiting for APIM deletion to complete...{Colors.RESET}")
        for i in range(360):  # 60 min max (10s intervals)
            check = subprocess.run(
                f'az apim show --name "{apim_name}" --resource-group "{resource_group}" --subscription "{subscription_id}" --query "provisioningState" --output tsv',
                capture_output=True, text=True, shell=True
            )
            if check.returncode != 0 or "NotFound" in check.stderr or not check.stdout.strip():
                print(f"  {Colors.GREEN}  APIM '{apim_name}' deleted.{Colors.RESET}")
                logger.log(f"APIM {apim_name} fully deleted after {i*10}s")
                break
            if i % 12 == 0:  # Every 2 min
                print(f"  {Colors.GRAY}  Still waiting for APIM deletion... ({i*10}s){Colors.RESET}")
            time.sleep(10)
        else:
            print(f"  {Colors.YELLOW}  Timed out waiting for APIM deletion — proceeding anyway{Colors.RESET}")
            logger.log(f"Timed out waiting for APIM {apim_name} deletion", "WARNING")

    return True


def destroy_byo_vnet(state, log_file):
    """Destroy BYO VNet or APIM foundry resources (based on foundry_type in state)."""
    foundry_label = get_foundry_label(state)
    tf_path = get_foundry_tf_path(state)
    print(f"\n{Colors.CYAN}=== Destroying {foundry_label} Resources ==={Colors.RESET}")
    logger.log(f"Starting {foundry_label} destruction (path: {tf_path})")

    byo_info = get_byo_resource_info(state)
    subscription_id = state["subscription_id"]

    # Step 1: Try terraform destroy
    print(f"\n{Colors.YELLOW}[1/5] Terraform Destroy{Colors.RESET}")
    tf_success, tf_output = run_terraform_destroy(tf_path, subscription_id, log_file)

    if tf_success:
        print(f"  {Colors.GREEN}[OK] Terraform destroy completed{Colors.RESET}")
    else:
        print(f"  {Colors.YELLOW}[WARN] Terraform destroy failed or incomplete{Colors.RESET}")
        logger.log(f"Terraform destroy failed: {tf_output[:500]}", "WARNING")

    # Step 2: For APIM deployments, explicitly delete APIM first so its VNet NICs are
    # fully removed before the RG delete is issued. Without this, az group delete hangs
    # for 30-45 min waiting for VNet de-injection and typically times out.
    if state.get("foundry_type") == "apim" and byo_info["resource_group"]:
        print(f"\n{Colors.YELLOW}[2/5] Pre-Delete APIM (required before RG deletion){Colors.RESET}")
        delete_apim_instances(byo_info["resource_group"], subscription_id, log_file)

    # Step 3: Always delete the resource group to catch any resources not in TF state
    # (e.g. APIM that finished provisioning after a failed/crashed apply)
    print(f"\n{Colors.YELLOW}[3/5] Delete Resource Group{Colors.RESET}")
    rg_name = byo_info["resource_group"]
    if rg_name:
        rg_success, rg_output = delete_resource_group(rg_name, subscription_id, log_file)
        if rg_success:
            print(f"  {Colors.GREEN}[OK] Resource group '{rg_name}' deleted (or already gone){Colors.RESET}")
        else:
            print(f"  {Colors.RED}[FAIL] Resource group deletion failed: {rg_output}{Colors.RESET}")
            if not tf_success:
                # Both TF destroy and RG deletion failed — offer state cleanup so user can retry
                if "Timeout" in rg_output and confirm("Delete terraform state files anyway? (Allows fresh start once RG is deleted)"):
                    removed = remove_terraform_state(tf_path, log_file)
                    if removed:
                        print(f"  {Colors.GREEN}[OK] Removed: {', '.join(removed)}{Colors.RESET}")
                        print(f"  {Colors.YELLOW}Note: Wait for RG deletion to complete in Azure, then run Deploy.{Colors.RESET}")
                return False
    else:
        print(f"  {Colors.GRAY}No resource group name found, skipping deletion{Colors.RESET}")

    # Wait for resources to appear as soft-deleted before purge
    print(f"\n{Colors.YELLOW}Waiting 60 seconds for resources to appear as soft-deleted...{Colors.RESET}")
    for i in range(6):
        time.sleep(10)
        print(f"  {Colors.GRAY}{(i+1)*10}s...{Colors.RESET}")

    # Step 4: Purge cognitive services
    print(f"\n{Colors.YELLOW}[4/5] Purge Cognitive Services{Colors.RESET}")
    if byo_info["ai_foundry_name"]:
        purge_success, purge_output = purge_cognitive_services(
            byo_info["ai_foundry_name"],
            byo_info["resource_group"],
            byo_info["location"],
            subscription_id,
            log_file
        )
        if purge_success:
            print(f"  {Colors.GREEN}[OK] Cognitive services purged{Colors.RESET}")
        else:
            print(f"  {Colors.YELLOW}[WARN] Purge may have failed: {purge_output[:200]}{Colors.RESET}")
    else:
        print(f"  {Colors.GRAY}No AI Foundry name found, skipping purge{Colors.RESET}")

    # Step 5: Remove terraform state
    print(f"\n{Colors.YELLOW}[5/5] Clean Up Terraform State{Colors.RESET}")
    removed = remove_terraform_state(tf_path, log_file)
    if removed:
        print(f"  {Colors.GREEN}[OK] Removed: {', '.join(removed)}{Colors.RESET}")
    else:
        print(f"  {Colors.GRAY}No state files to remove{Colors.RESET}")

    # Also clean up the other foundry path's state if stale files exist
    other_path = BYO_VNET_PATH if tf_path == FOUNDRY_APIM_PATH else FOUNDRY_APIM_PATH
    if (other_path / "terraform.tfstate").exists():
        remove_terraform_state(other_path, log_file)

    # Update state - reset step and clear resource info
    state = update_step(state, "byo_vnet", "pending")
    if "resources" in state:
        state["resources"]["byo_vnet_rg"] = None
        state["resources"]["ai_foundry_name"] = None
        state["resources"]["ai_foundry_project_name"] = None
        save_state(state)
    
    print(f"\n{Colors.GREEN}BYO VNet destruction complete!{Colors.RESET}")
    logger.log("BYO VNet destruction completed")
    return True


def destroy_hub_spoke(state, log_file):
    """Destroy Hub-Spoke resources."""
    print(f"\n{Colors.CYAN}=== Destroying Hub-Spoke Network ==={Colors.RESET}")
    logger.log("Starting Hub-Spoke destruction")
    
    hub_info = get_hub_spoke_resource_info(state)
    subscription_id = state["subscription_id"]
    
    # Step 1: Try terraform destroy
    print(f"\n{Colors.YELLOW}[1/5] Terraform Destroy{Colors.RESET}")
    tf_success, tf_output = run_terraform_destroy(HUB_SPOKE_PATH, subscription_id, log_file)
    
    if tf_success:
        print(f"  {Colors.GREEN}[OK] Terraform destroy completed{Colors.RESET}")
    else:
        print(f"  {Colors.YELLOW}[WARN] Terraform destroy failed, falling back to resource group deletion{Colors.RESET}")
        logger.log(f"Terraform destroy failed: {tf_output[:500]}", "WARNING")
        
        # Fall back to RG deletion
        if hub_info["resource_group"]:
            print(f"\n{Colors.YELLOW}[2/5] Delete Resource Group{Colors.RESET}")
            rg_success, rg_output = delete_resource_group(hub_info["resource_group"], subscription_id, log_file)
            
            if rg_success:
                print(f"  {Colors.GREEN}[OK] Resource group deleted{Colors.RESET}")
            else:
                print(f"  {Colors.RED}[FAIL] Resource group deletion failed: {rg_output}{Colors.RESET}")
                
                # Offer to clean up state files anyway (RG may be deleting in background)
                if "Timeout" in rg_output and confirm("Delete terraform state files anyway? (Allows fresh start once RG is deleted)"):
                    removed = remove_terraform_state(HUB_SPOKE_PATH, log_file)
                    if removed:
                        print(f"  {Colors.GREEN}[OK] Removed: {', '.join(removed)}{Colors.RESET}")
                        print(f"  {Colors.YELLOW}Note: Wait for RG deletion to complete in Azure, then run Deploy.{Colors.RESET}")
                return False
        else:
            print(f"  {Colors.YELLOW}[WARN] Could not determine resource group name{Colors.RESET}")
    
    # Step 3: Remove terraform state
    print(f"\n{Colors.YELLOW}[3/5] Clean Up Terraform State{Colors.RESET}")
    removed = remove_terraform_state(HUB_SPOKE_PATH, log_file)
    if removed:
        print(f"  {Colors.GREEN}[OK] Removed: {', '.join(removed)}{Colors.RESET}")
    else:
        print(f"  {Colors.GRAY}No state files to remove{Colors.RESET}")
    
    # Step 4: Remove VPN client files
    print(f"\n{Colors.YELLOW}[4/5] Clean Up VPN Client Files{Colors.RESET}")
    removed = remove_vpn_client_files(log_file)
    if removed:
        print(f"  {Colors.GREEN}[OK] Removed: {', '.join(removed)}{Colors.RESET}")
    else:
        print(f"  {Colors.GRAY}No VPN client files to remove{Colors.RESET}")
    
    # Step 5: Remove VPN connection profile
    print(f"\n{Colors.YELLOW}[5/5] Remove VPN Connection Profile{Colors.RESET}")
    removed = remove_vpn_connection_profile(log_file)
    if removed:
        print(f"  {Colors.GREEN}[OK] Removed: {', '.join(removed)}{Colors.RESET}")
    else:
        print(f"  {Colors.GRAY}No VPN connections found{Colors.RESET}")
    
    # Update state - reset all steps and clear resource info
    state = update_step(state, "hub_spoke", "pending")
    state = update_step(state, "dns_install", "pending")
    state = update_step(state, "cert_install", "pending")
    state = update_step(state, "vpn_client", "pending")
    if "resources" in state:
        state["resources"]["hub_spoke_rg"] = None
        state["resources"]["vpn_gateway_name"] = None
        save_state(state)
    
    print(f"\n{Colors.GREEN}Hub-Spoke destruction complete!{Colors.RESET}")
    logger.log("Hub-Spoke destruction completed")
    return True


def show_destroy_menu(state):
    """Show destroy options menu and return choice."""
    byo_status = state["steps"].get("byo_vnet", {}).get("status", "pending")
    hub_status = state["steps"].get("hub_spoke", {}).get("status", "pending")
    foundry_label = get_foundry_label(state)

    # Resources exist if completed, failed, or in_progress (partial deployment)
    byo_deployed = byo_status in ("completed", "failed", "in_progress")
    hub_deployed = hub_status in ("completed", "failed", "in_progress")

    print(f"\n{Colors.RED}=== Destroy Resources ==={Colors.RESET}")
    print(f"\n  Current deployment status:")
    print(f"    Hub-Spoke Network: {Colors.GREEN if hub_status == 'completed' else Colors.YELLOW if hub_status in ('failed', 'in_progress') else Colors.GRAY}{hub_status}{Colors.RESET}")
    print(f"    {foundry_label}: {Colors.GREEN if byo_status == 'completed' else Colors.YELLOW if byo_status in ('failed', 'in_progress') else Colors.GRAY}{byo_status}{Colors.RESET}")

    if not byo_deployed and not hub_deployed:
        print(f"\n  {Colors.YELLOW}No resources to destroy. All steps are pending.{Colors.RESET}")
        input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")
        return None

    print(f"\n  {Colors.YELLOW}Destroy Options:{Colors.RESET}")

    options = []
    if byo_deployed:
        options.append(("1", f"Destroy {foundry_label} only"))
    if byo_deployed or hub_deployed:
        options.append(("2", f"Destroy ALL ({foundry_label} + Hub-Spoke Network)"))
    options.append(("0", "Cancel - return to menu"))

    for opt, desc in options:
        print(f"    [{opt}] {desc}")

    while True:
        choice = input(f"\n{Colors.YELLOW}  Select option: {Colors.RESET}").strip().lower()

        if choice == "0":
            return "cancel"
        elif choice == "1" and byo_deployed:
            return "byo_only"
        elif choice == "2":
            return "all"
        else:
            print(f"  {Colors.RED}Invalid option. Please try again.{Colors.RESET}")


def confirm_destroy(destroy_type, state):
    """Show what will be destroyed and confirm."""
    byo_info = get_byo_resource_info(state)
    hub_info = get_hub_spoke_resource_info(state)
    foundry_label = get_foundry_label(state)

    print(f"\n{Colors.RED}{'='*60}")
    print(f"  WARNING: The following resources will be DESTROYED")
    print(f"{'='*60}{Colors.RESET}")

    if destroy_type in ("byo_only", "all"):
        print(f"\n  {Colors.YELLOW}{foundry_label}:{Colors.RESET}")
        print(f"    - Resource Group: {byo_info['resource_group']}")
        print(f"    - AI Foundry: {byo_info['ai_foundry_name'] or 'unknown'}")
        print(f"    - All resources in the group (Storage, CosmosDB, AI Search, etc.)")
        if state.get("foundry_type") == "apim":
            print(f"    - API Management instance")

    if destroy_type == "all":
        print(f"\n  {Colors.YELLOW}Hub-Spoke Network:{Colors.RESET}")
        print(f"    - Resource Group: {hub_info['resource_group'] or 'unknown'}")
        print(f"    - VPN Gateway, DNS VM, VNets, NSGs, etc.")
        print(f"    - VPN client files and connection profile")

    print(f"\n{Colors.RED}This action cannot be undone!{Colors.RESET}")

    confirm_text = "DESTROY"
    response = input(f"\n{Colors.YELLOW}Type '{confirm_text}' to confirm: {Colors.RESET}").strip()

    return response.upper() == confirm_text


def run_destroy():
    """Run the destroy workflow."""
    state = load_state()
    
    if not state:
        print(f"\n{Colors.YELLOW}No deployment state found. Nothing to destroy.{Colors.RESET}")
        input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")
        return
    
    # Initialize logging with "destroy" prefix
    log_file = logger.initialize("destroy")
    logger.log("Destroy operation started")
    
    # Show destroy menu
    choice = show_destroy_menu(state)
    
    if choice is None or choice == "cancel":
        return
    
    # Confirm destruction
    if not confirm_destroy(choice, state):
        print(f"\n{Colors.YELLOW}Destruction cancelled.{Colors.RESET}")
        return
    
    # Execute destruction
    if choice == "byo_only":
        success = destroy_byo_vnet(state, log_file)
    elif choice == "all":
        # Destroy BYO first
        byo_status = state["steps"].get("byo_vnet", {}).get("status", "pending")
        if byo_status in ("completed", "failed"):
            success = destroy_byo_vnet(state, log_file)
            if success:
                # Wait before destroying hub-spoke to allow purge to complete
                print(f"\n{Colors.YELLOW}Waiting 120 seconds before destroying Hub-Spoke...{Colors.RESET}")
                for i in range(12):
                    time.sleep(10)
                    print(f"  {Colors.GRAY}{(i+1)*10}s...{Colors.RESET}")
            else:
                print(f"\n{Colors.RED}BYO VNet destruction failed. Aborting.{Colors.RESET}")
                return
        
        # Reload state (may have been updated)
        state = load_state()
        success = destroy_hub_spoke(state, log_file)
    
    if success:
        print(f"\n{Colors.GREEN}{'='*60}")
        print(f"  Destruction Complete!")
        print(f"  Log file: {log_file}")
        print(f"{'='*60}{Colors.RESET}")
    else:
        print(f"\n{Colors.RED}Destruction encountered errors. Check log: {log_file}{Colors.RESET}")
    
    input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")


def show_main_menu():
    """Show main menu and return choice."""
    state = load_state()
    has_deployment = has_previous_deployment()
    has_destroyable = has_resources_to_destroy()
    has_state_files = has_terraform_state_files()

    # Option [4] available when Step 5 is not yet completed (can reselect BYO vs APIM)
    step5_pending = (
        has_deployment and
        state.get("steps", {}).get("byo_vnet", {}).get("status") != "completed"
    )

    def _print_menu():
        print(f"\n  {Colors.YELLOW}Options:{Colors.RESET}")
        print(f"    [1] Deploy - Start or resume deployment")
        if has_destroyable:
            print(f"    [2] Destroy - Remove deployed resources")
        else:
            print(f"    {Colors.GRAY}[2] Destroy - No resources to destroy{Colors.RESET}")
        if has_state_files:
            print(f"    [3] Reset - Delete all state files (fresh start)")
        else:
            print(f"    {Colors.GRAY}[3] Reset - No state files to delete{Colors.RESET}")
        if step5_pending:
            current = state.get("foundry_type")
            current_hint = f" (current: {get_foundry_label(state)})" if current else ""
            print(f"    [4] Reselect Foundry Type - Change BYO vs APIM{current_hint}")
        else:
            print(f"    {Colors.GRAY}[4] Reselect Foundry Type - Not available (Step 5 completed or not started){Colors.RESET}")
        print(f"    [0] Quit")

    print(f"\n{Colors.CYAN}=== Main Menu ==={Colors.RESET}")
    if has_deployment:
        completed = count_completed(state)
        print(f"\n  {Colors.GRAY}Previous deployment: {completed}/{TOTAL_STEPS} steps completed{Colors.RESET}")
    _print_menu()

    while True:
        choice = input(f"\n{Colors.YELLOW}  Select option: {Colors.RESET}").strip().lower()

        if choice == "1":
            return "deploy"
        elif choice == "2":
            if has_destroyable:
                return "destroy"
            else:
                print(f"  {Colors.YELLOW}No resources to destroy.{Colors.RESET}")
        elif choice == "3":
            if has_state_files:
                return "reset"
            else:
                print(f"  {Colors.YELLOW}No state files to delete.{Colors.RESET}")
        elif choice == "4":
            if step5_pending:
                return "reselect_foundry"
            else:
                print(f"  {Colors.YELLOW}Not available: Step 5 is already completed or deployment hasn't started.{Colors.RESET}")
        elif choice == "0":
            return "quit"
        else:
            print(f"  {Colors.RED}Invalid option. Please try again.{Colors.RESET}")
        _print_menu()


# Prerequisites Check
def compare_versions(version1, version2):
    """Compare two version strings. Returns -1, 0, or 1."""
    v1_parts = [int(x) for x in version1.split('.')]
    v2_parts = [int(x) for x in version2.split('.')]
    
    for i in range(max(len(v1_parts), len(v2_parts))):
        v1 = v1_parts[i] if i < len(v1_parts) else 0
        v2 = v2_parts[i] if i < len(v2_parts) else 0
        if v1 < v2:
            return -1
        elif v1 > v2:
            return 1
    return 0


def _refresh_path():
    """Refresh os.environ['PATH'] from the registry so newly installed tools are found."""
    try:
        import winreg
        # Read Machine PATH
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as key:
            machine_path, _ = winreg.QueryValueEx(key, "Path")
        # Read User PATH
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            user_path, _ = winreg.QueryValueEx(key, "Path")
        os.environ["PATH"] = machine_path + ";" + user_path
    except Exception:
        pass  # Non-Windows or registry read failed; keep existing PATH
    
    # Ensure critical Windows system paths are included (required for cmd.exe, used by Azure SDK)
    critical_paths = [
        r"C:\Windows\System32",
        r"C:\Windows",
    ]
    
    # Also add common installation paths that might not be in registry yet
    common_paths = [
        os.path.expandvars(r"%ProgramFiles%\Microsoft SDKs\Azure\CLI2\wbin"),  # Azure CLI
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft SDKs\Azure\CLI2\wbin"),  # Azure CLI x86
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin"),  # VS Code
    ]
    
    current_path = os.environ.get("PATH", "")
    
    # Add critical paths first (prepend to ensure they're found)
    for path in critical_paths:
        if os.path.isdir(path) and path.lower() not in current_path.lower():
            os.environ["PATH"] = path + ";" + current_path
            current_path = os.environ["PATH"]
    
    # Add common paths
    for path in common_paths:
        if os.path.isdir(path) and path not in current_path:
            os.environ["PATH"] = path + ";" + current_path
            current_path = os.environ["PATH"]
    
    # Ensure COMSPEC is set (required by Azure SDK's ChainedTokenCredential)
    if "COMSPEC" not in os.environ:
        os.environ["COMSPEC"] = r"C:\Windows\System32\cmd.exe"


def check_prerequisites():
    """Check if required tools are installed."""
    results = {"all_passed": True, "details": []}
    logger.log("Starting prerequisite checks")
    
    # Check Terraform (with minimum version)
    tf_check = {"name": "Terraform", "installed": False, "version": None, "version_ok": False}
    try:
        result = subprocess.run(["terraform", "--version"], capture_output=True, text=True, timeout=10)
        logger.log(f"Terraform check: returncode={result.returncode}, stdout={result.stdout[:200] if result.stdout else 'empty'}")
        if result.returncode == 0:
            match = re.search(r"Terraform v(\d+\.\d+\.\d+)", result.stdout)
            if match:
                tf_check["installed"] = True
                tf_check["version"] = match.group(1)
                # Check minimum version
                if compare_versions(tf_check["version"], MIN_TERRAFORM_VERSION) >= 0:
                    tf_check["version_ok"] = True
    except Exception as e:
        logger.log(f"Terraform check exception: {e}", "ERROR")
    results["details"].append(tf_check)
    logger.log(f"Terraform: installed={tf_check['installed']}, version={tf_check['version']}, version_ok={tf_check.get('version_ok')}")
    if not tf_check["installed"] or not tf_check["version_ok"]:
        results["all_passed"] = False
    
    # Check Azure CLI (use shell=True on Windows because az is az.cmd)
    # Note: az --version can be slow on some machines; use a larger timeout and fall back
    # to az account show to confirm CLI is present if version check times out.
    az_check = {"name": "Azure CLI", "installed": False, "version": None}
    try:
        result = subprocess.run("az --version", capture_output=True, text=True, timeout=60, shell=True)
        logger.log(f"Azure CLI check: returncode={result.returncode}, stderr={result.stderr[:200] if result.stderr else 'empty'}")
        if result.returncode == 0:
            match = re.search(r"azure-cli\s+(\d+\.\d+\.\d+)", result.stdout)
            if match:
                az_check["installed"] = True
                az_check["version"] = match.group(1)
    except Exception as e:
        logger.log(f"Azure CLI check exception: {e}", "ERROR")
    results["details"].append(az_check)
    logger.log(f"Azure CLI: installed={az_check['installed']}, version={az_check['version']}")
    # CLI install status is re-evaluated after login check below (login success implies CLI is present)

    # Check Azure CLI login
    login_check = {"name": "Azure CLI Login", "installed": False, "version": None}
    try:
        result = subprocess.run("az account show", capture_output=True, text=True, timeout=30, shell=True)
        logger.log(f"Azure CLI login check: returncode={result.returncode}, stderr={result.stderr[:200] if result.stderr else 'empty'}")
        if result.returncode == 0:
            account = json.loads(result.stdout)
            login_check["installed"] = True
            login_check["version"] = f"Logged in as: {account.get('user', {}).get('name', 'unknown')}"
            # If az --version timed out but login works, CLI is clearly installed
            if not az_check["installed"]:
                az_check["installed"] = True
                az_check["version"] = "unknown (version check timed out)"
                logger.log("Azure CLI: marking installed=True because login succeeded")
    except Exception as e:
        logger.log(f"Azure CLI login check exception: {e}", "ERROR")
    results["details"].append(login_check)
    logger.log(f"Azure CLI Login: logged_in={login_check['installed']}, user={login_check['version']}")
    if not az_check["installed"]:
        results["all_passed"] = False
    if not login_check["installed"]:
        results["all_passed"] = False
    
    # Check OpenSSL (required for VPN certificate installation)
    openssl_check = {"name": "OpenSSL", "installed": False, "version": None}
    try:
        result = subprocess.run(["openssl", "version"], capture_output=True, text=True, timeout=10)
        logger.log(f"OpenSSL check: returncode={result.returncode}, stdout={result.stdout[:200] if result.stdout else 'empty'}")
        if result.returncode == 0:
            match = re.search(r"OpenSSL\s+([\d\.]+)", result.stdout)
            if match:
                openssl_check["installed"] = True
                openssl_check["version"] = match.group(1)
    except Exception as e:
        logger.log(f"OpenSSL check exception: {e}", "ERROR")
    results["details"].append(openssl_check)
    logger.log(f"OpenSSL: installed={openssl_check['installed']}, version={openssl_check['version']}")
    if not openssl_check["installed"]:
        results["all_passed"] = False
    
    logger.log(f"Prerequisite check complete: all_passed={results['all_passed']}")
    return results


def show_prerequisites(results):
    """Display prerequisites check results."""
    for check in results["details"]:
        if check["name"] == "Terraform":
            # Special handling for Terraform with version check
            if check["installed"] and check.get("version_ok", True):
                print(f"  {Colors.GREEN}[OK] {check['name']} - {check['version']} (minimum: {MIN_TERRAFORM_VERSION}){Colors.RESET}")
            elif check["installed"] and not check.get("version_ok", True):
                print(f"  {Colors.RED}[FAIL] {check['name']} - {check['version']} (minimum {MIN_TERRAFORM_VERSION} required){Colors.RESET}")
            else:
                print(f"  {Colors.RED}[FAIL] {check['name']} - not found (minimum {MIN_TERRAFORM_VERSION} required){Colors.RESET}")
        elif check["installed"]:
            version = f"- {check['version']}" if check["version"] else ""
            print(f"  {Colors.GREEN}[OK] {check['name']} {version}{Colors.RESET}")
        else:
            print(f"  {Colors.RED}[FAIL] {check['name']} - not found{Colors.RESET}")
    
    return results["all_passed"]


def get_missing_prerequisites(results):
    """Get list of missing prerequisites that can be auto-installed or upgraded."""
    missing = []
    install_commands = {
        "Terraform": "Hashicorp.Terraform",
        "Azure CLI": "Microsoft.AzureCLI",
        "OpenSSL": "FireDaemon.OpenSSL",
    }
    
    for check in results["details"]:
        if check["name"] in install_commands:
            if not check["installed"]:
                missing.append({
                    "name": check["name"],
                    "winget_id": install_commands[check["name"]],
                    "action": "install"
                })
            elif check["name"] == "Terraform" and not check.get("version_ok", True):
                missing.append({
                    "name": check["name"],
                    "winget_id": install_commands[check["name"]],
                    "action": "upgrade",
                    "current_version": check["version"]
                })
    
    return missing


def install_prerequisites(missing):
    """Install or upgrade missing prerequisites using winget."""
    print(f"\n{Colors.CYAN}Installing/upgrading prerequisites...{Colors.RESET}")
    
    for item in missing:
        action = item.get("action", "install")
        if action == "upgrade":
            print(f"\n  {Colors.YELLOW}Upgrading {item['name']} (current: {item.get('current_version', 'unknown')}, required: {MIN_TERRAFORM_VERSION})...{Colors.RESET}")
            print(f"  {Colors.GRAY}Running: winget upgrade {item['winget_id']}{Colors.RESET}")
            
            result = subprocess.run(
                f"winget upgrade --id {item['winget_id']} --accept-source-agreements --accept-package-agreements",
                shell=True,
                capture_output=False,
                text=True
            )
        else:
            print(f"\n  {Colors.YELLOW}Installing {item['name']}...{Colors.RESET}")
            print(f"  {Colors.GRAY}Running: winget install {item['winget_id']}{Colors.RESET}")
            
            result = subprocess.run(
                f"winget install --id {item['winget_id']} --accept-source-agreements --accept-package-agreements",
                shell=True,
                capture_output=False,
                text=True
            )
        
        if result.returncode == 0:
            print(f"  {Colors.GREEN}[OK] {item['name']} {action}d{Colors.RESET}")
        else:
            print(f"  {Colors.RED}[FAIL] {item['name']} {action} failed{Colors.RESET}")
            if action == "upgrade":
                print(f"  {Colors.YELLOW}Try manually: winget upgrade {item['winget_id']}{Colors.RESET}")
            else:
                print(f"  {Colors.YELLOW}Try manually: winget install {item['winget_id']}{Colors.RESET}")
    
    # Refresh PATH so newly installed tools are found without restarting
    _refresh_path()

    # Check if Azure CLI login is needed
    print(f"\n{Colors.GRAY}Re-checking prerequisites...{Colors.RESET}")


def run_azure_login():
    """Run az login interactively."""
    print(f"\n{Colors.CYAN}Starting Azure login...{Colors.RESET}")
    print(f"  {Colors.GRAY}A browser window will open for authentication.{Colors.RESET}")
    
    result = subprocess.run(
        "az login",
        shell=True,
        capture_output=False  # Show output to user
    )
    
    return result.returncode == 0


def check_and_register_resource_providers(state):
    """Check and register required Azure Resource Providers for AI Foundry deployment.
    
    Args:
        state: Deployment state dict (will be updated if providers are registered)
    
    Returns:
        bool: True if all providers are registered, False if registration failed or was declined.
    """
    # Check if already verified for this subscription
    if state.get("rp_registered"):
        print(f"\n  {Colors.GREEN}Resource providers already verified for this subscription.{Colors.RESET}")
        logger.log("Resource providers already verified (cached)")
        return True
    
    subscription_id = state["subscription_id"]
    print(f"\n  {Colors.CYAN}Checking Azure Resource Providers...{Colors.RESET}")
    logger.log(f"Checking resource providers for subscription {subscription_id}")
    
    # Check which providers need registration
    missing_providers = []
    for provider in REQUIRED_RESOURCE_PROVIDERS:
        try:
            result = subprocess.run(
                f'az provider show --namespace {provider} --query "registrationState" -o tsv',
                capture_output=True, text=True, timeout=30, shell=True
            )
            status = result.stdout.strip().lower()
            logger.log(f"RP check {provider}: status={status}")
            
            if result.returncode != 0 or status != "registered":
                missing_providers.append(provider)
                print(f"    {Colors.YELLOW}[MISSING] {provider}{Colors.RESET}")
            else:
                print(f"    {Colors.GREEN}[OK] {provider}{Colors.RESET}")
        except Exception as e:
            logger.log(f"RP check {provider} exception: {e}", "ERROR")
            missing_providers.append(provider)
            print(f"    {Colors.YELLOW}[UNKNOWN] {provider}{Colors.RESET}")
    
    if not missing_providers:
        print(f"  {Colors.GREEN}All required resource providers are registered.{Colors.RESET}")
        logger.log("All resource providers already registered")
        # Cache the result in state
        state["rp_registered"] = True
        save_state(state)
        return True
    
    # Offer to register missing providers
    print(f"\n  {Colors.YELLOW}The following resource providers need to be registered:{Colors.RESET}")
    for provider in missing_providers:
        print(f"    - {provider}")
    print(f"  {Colors.GRAY}These are required for AI Foundry with Standard Agents.{Colors.RESET}")
    
    if not confirm("\n  Register these resource providers now?"):
        print(f"\n  {Colors.YELLOW}Manual commands:{Colors.RESET}")
        for provider in missing_providers:
            print(f"  {Colors.GRAY}az provider register --namespace {provider}{Colors.RESET}")
        return False
    
    # Register missing providers
    print(f"\n  {Colors.CYAN}Registering resource providers...{Colors.RESET}")
    print(f"  {Colors.GRAY}(This may take a few minutes){Colors.RESET}")
    
    for provider in missing_providers:
        logger.log(f"Registering resource provider: {provider}")
        result = subprocess.run(
            f"az provider register --namespace {provider}",
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"    {Colors.GREEN}[OK] {provider} registration initiated{Colors.RESET}")
            logger.log(f"Resource provider {provider} registration initiated")
        else:
            print(f"    {Colors.RED}[FAIL] {provider} registration failed: {result.stderr}{Colors.RESET}")
            logger.log(f"Resource provider {provider} registration failed: {result.stderr}", "ERROR")
    
    # Wait for registrations to complete
    print(f"\n  {Colors.GRAY}Waiting for registrations to complete...{Colors.RESET}")
    max_wait = 180  # 3 minutes max
    wait_interval = 15
    elapsed = 0
    
    while elapsed < max_wait:
        all_registered = True
        pending = []
        for provider in missing_providers:
            result = subprocess.run(
                f'az provider show --namespace {provider} --query "registrationState" -o tsv',
                capture_output=True, text=True, timeout=30, shell=True
            )
            if result.stdout.strip().lower() != "registered":
                all_registered = False
                pending.append(provider)
        
        if all_registered:
            print(f"  {Colors.GREEN}All resource providers registered successfully!{Colors.RESET}")
            logger.log("All resource providers registered successfully")
            # Cache the result in state
            state["rp_registered"] = True
            save_state(state)
            return True
        
        time.sleep(wait_interval)
        elapsed += wait_interval
        print(f"  {Colors.GRAY}Still waiting for: {', '.join(pending)} ({elapsed}s){Colors.RESET}")
    
    print(f"  {Colors.YELLOW}Registration taking longer than expected. Proceeding anyway - Terraform will wait if needed.{Colors.RESET}")
    logger.log("Resource provider registration timeout - proceeding anyway", "WARNING")
    # Still cache as registered since we're proceeding - Terraform will handle any remaining wait
    state["rp_registered"] = True
    save_state(state)
    return True  # Return True to allow deployment to proceed - Terraform has its own wait logic


def handle_missing_prerequisites(results):
    """Handle missing prerequisites - offer to install or show manual instructions."""
    missing = get_missing_prerequisites(results)
    
    # Check if only login is missing
    login_missing = any(c["name"] == "Azure CLI Login" and not c["installed"] for c in results["details"])
    tools_missing = len(missing) > 0
    
    if tools_missing:
        # Build description of what needs to be done
        installs = [m["name"] for m in missing if m.get("action") == "install"]
        upgrades = [m["name"] for m in missing if m.get("action") == "upgrade"]
        
        if installs and upgrades:
            print(f"\n{Colors.YELLOW}Missing/outdated tools can be fixed automatically using winget.{Colors.RESET}")
            print(f"  To install: {', '.join(installs)}")
            print(f"  To upgrade: {', '.join(upgrades)}")
        elif upgrades:
            print(f"\n{Colors.YELLOW}Outdated tools can be upgraded automatically using winget.{Colors.RESET}")
            print(f"  To upgrade: {', '.join(upgrades)}")
        else:
            print(f"\n{Colors.YELLOW}Missing tools can be installed automatically using winget.{Colors.RESET}")
            print(f"  To install: {', '.join(installs)}")
        
        if confirm("\n  Install/upgrade now?"):
            install_prerequisites(missing)
            
            # Re-check after installation
            new_results = check_prerequisites()
            show_prerequisites(new_results)
            
            if new_results["all_passed"]:
                return True
            
            # Check if only login is missing now
            login_missing = any(c["name"] == "Azure CLI Login" and not c["installed"] for c in new_results["details"])
            if login_missing and all(c["installed"] and c.get("version_ok", True) for c in new_results["details"] if c["name"] != "Azure CLI Login"):
                # Offer to run az login
                if confirm("\n  Login to Azure now?"):
                    if run_azure_login():
                        return True
                    else:
                        print(f"\n{Colors.RED}Azure login failed. Please try 'az login' manually.{Colors.RESET}")
                        return False
                print(f"\n{Colors.YELLOW}Please run 'az login' to authenticate.{Colors.RESET}")
                return False
            
            print(f"\n{Colors.RED}Some prerequisites still missing after installation.{Colors.RESET}")
            return False
        else:
            print(f"\n{Colors.YELLOW}Manual commands:{Colors.RESET}")
            for m in missing:
                if m.get("action") == "upgrade":
                    print(f"{Colors.GRAY}  winget upgrade {m['winget_id']}{Colors.RESET}")
                else:
                    print(f"{Colors.GRAY}  winget install {m['winget_id']}{Colors.RESET}")
            if login_missing:
                print(f"{Colors.GRAY}  az login{Colors.RESET}")
            return False
    
    if login_missing:
        if confirm("\n  Login to Azure now?"):
            if run_azure_login():
                return True
            else:
                print(f"\n{Colors.RED}Azure login failed. Please try 'az login' manually.{Colors.RESET}")
                return False
        print(f"\n{Colors.YELLOW}Please run 'az login' to authenticate with Azure.{Colors.RESET}")
        return False
    
    return True


def _try_import_existing_resources(output, env, log_file):
    """Detect 'already exists' errors in terraform output and import those resources.
    
    Returns True if at least one resource was successfully imported (caller should retry apply).
    """
    import re
    import time

    # terraform error format:
    #   Error: a resource with the ID "..." already exists ...
    #     with azurerm_api_management.apim,
    pattern = re.compile(
        r'resource with the ID "([^"]+)" already exists.*?with ([\w.]+),',
        re.DOTALL
    )

    matches = list(pattern.finditer(output))
    if not matches:
        return False

    imported_any = False
    for match in matches:
        resource_id = match.group(1)
        resource_address = match.group(2)

        print(f"  {Colors.YELLOW}Resource already exists in Azure: {resource_address}{Colors.RESET}")
        print(f"  {Colors.GRAY}Attempting to import into Terraform state…{Colors.RESET}")
        logger.log(f"Auto-importing existing resource: {resource_address} ({resource_id})")

        # Retry import — resource may still be activating (e.g. APIM takes 30-45 min)
        for import_attempt in range(1, 46):  # up to 45 min
            import_result = subprocess.run(
                ["terraform", "import", "-no-color", resource_address, resource_id],
                capture_output=True, text=True, env=env
            )
            import_output = import_result.stdout + import_result.stderr

            _append_to_log(log_file, import_output)

            if import_result.returncode == 0:
                print(f"  {Colors.GREEN}Imported {resource_address} successfully.{Colors.RESET}")
                logger.log(f"Import succeeded: {resource_address}")
                imported_any = True
                break
            elif "activating" in import_output.lower() or "not ready" in import_output.lower():
                print(f"  {Colors.YELLOW}Resource still activating. Waiting 60s (attempt {import_attempt}/45)…{Colors.RESET}")
                logger.log(f"Import attempt {import_attempt}: resource still activating, waiting 60s")
                time.sleep(60)
            else:
                print(f"  {Colors.RED}Import failed for {resource_address}. Check log for details.{Colors.RESET}")
                logger.log(f"Import failed: {import_output[-500:]}")
                break

    return imported_any


# Terraform Operations
def run_terraform(working_dir, subscription_id, variables, log_file, max_retries=2):
    """Run terraform init and apply with retry logic."""
    original_dir = os.getcwd()
    os.chdir(working_dir)
    
    try:
        # Set environment variable
        env = os.environ.copy()
        env["ARM_SUBSCRIPTION_ID"] = subscription_id
        
        # Ensure critical Windows system paths are present (required for Azure CLI credential chain)
        system_root = os.environ.get("SystemRoot", r"C:\WINDOWS")
        critical_paths = [
            os.path.join(system_root, "system32"),
            system_root,
        ]
        current_path = env.get("PATH", "")
        for critical_path in critical_paths:
            if critical_path.lower() not in current_path.lower():
                current_path = critical_path + ";" + current_path
        env["PATH"] = current_path
        
        # Create tfvars content
        tfvars_lines = [f'subscription_id = "{subscription_id}"']
        for key, value in variables.items():
            if isinstance(value, bool):
                tfvars_lines.append(f'{key} = {str(value).lower()}')
            elif isinstance(value, int):
                tfvars_lines.append(f'{key} = {value}')
            else:
                tfvars_lines.append(f'{key} = "{value}"')
        
        with open("terraform.tfvars", "w", encoding="utf-8") as f:
            f.write("\n".join(tfvars_lines))
        
        # Initialize
        print(f"  {Colors.GRAY}Initializing Terraform...{Colors.RESET}")
        result = subprocess.run(
            ["terraform", "init", "-no-color"],
            capture_output=True, text=True, env=env
        )
        
        _append_to_log(log_file, result.stdout + result.stderr)
        
        if result.returncode != 0:
            return {"success": False, "error": "Terraform init failed", "output": result.stderr}
        
        # Apply with retries
        imported_resources = False
        for attempt in range(1, max_retries + 2):  # +1 slot reserved for post-import retry
            print(f"  {Colors.GRAY}Applying Terraform (attempt {attempt})...{Colors.RESET}")
            
            result = subprocess.run(
                ["terraform", "apply", "-auto-approve", "-no-color"],
                capture_output=True, text=True, env=env
            )
            
            _append_to_log(log_file, result.stdout + result.stderr)
            
            if result.returncode == 0:
                return {"success": True, "output": result.stdout}
            
            combined = result.stdout + result.stderr

            # Auto-import resources that already exist in Azure but not in TF state
            # (happens when a prior run failed mid-way and Azure kept provisioning)
            if not imported_resources and "already exists" in combined:
                if _try_import_existing_resources(combined, env, log_file):
                    imported_resources = True
                    print(f"  {Colors.CYAN}Retrying apply after successful import(s)...{Colors.RESET}")
                    continue  # immediate retry — don't sleep

            if attempt <= max_retries:
                print(f"  {Colors.YELLOW}Terraform apply failed. Retrying in 10 seconds...{Colors.RESET}")
                import time
                time.sleep(10)
        
        # Show last lines on failure
        print(f"\n  {Colors.RED}Last terraform output:{Colors.RESET}")
        for line in (result.stdout + result.stderr).split("\n")[-20:]:
            print(f"  {Colors.GRAY}{line}{Colors.RESET}")
        
        return {"success": False, "error": f"Terraform apply failed after {max_retries} attempts", "output": result.stderr}
    
    finally:
        os.chdir(original_dir)


def run_powershell_script(script_path, elevated=False, working_dir=None, script_args=None):
    """Run a PowerShell script from a specific directory.
    
    Args:
        script_path: Path to the PowerShell script
        elevated: Whether to run with admin elevation
        working_dir: Working directory for the script
        script_args: Optional string of arguments to pass to the script
    """
    script_path = Path(script_path).resolve()
    
    # Default working directory is the script's parent folder
    if working_dir is None:
        working_dir = script_path.parent
    
    # Log execution details for debugging
    logger.log(f"Running PowerShell script: {script_path}")
    logger.log(f"  Working directory: {working_dir}")
    logger.log(f"  Elevated: {elevated}")
    logger.log(f"  Script exists: {script_path.exists()}")
    if script_args:
        logger.log(f"  Script args: {script_args}")
    
    if elevated:
        # Run with elevation using a temp script to avoid quoting issues with paths containing spaces
        import tempfile
        
        # Create temp files for script and output capture
        temp_script = tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False, encoding='utf-8')
        temp_log = tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8')
        temp_log.close()
        
        # Write wrapper script that captures output to temp log file
        temp_script.write(f'$ErrorActionPreference = "Continue"\n')
        temp_script.write(f'Set-Location "{working_dir}"\n')
        temp_script.write(f'Start-Sleep -Seconds 2\n')
        temp_script.write(f'& "{script_path}" 2>&1 | Tee-Object -FilePath "{temp_log.name}"\n')
        temp_script.write(f'$exitCode = $LASTEXITCODE\n')
        temp_script.write(f'"EXIT_CODE:$exitCode" | Add-Content -Path "{temp_log.name}"\n')
        #temp_script.write(f'Read-Host "Press Enter to close..."\n')
        temp_script.close()
        
        try:
            cmd = [
                POWERSHELL_PATH, "-Command",
                f'Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "{temp_script.name}" -Wait'
            ]
            subprocess.run(cmd, capture_output=True, text=True)
            
            # Read the captured output
            output = ""
            exit_code = 0
            if os.path.exists(temp_log.name):
                with open(temp_log.name, 'r', encoding='utf-8', errors='replace') as f:
                    output = f.read()
                # Extract exit code from output
                for line in output.split('\n'):
                    if line.startswith('EXIT_CODE:'):
                        try:
                            exit_code = int(line.split(':')[1].strip())
                        except:
                            pass
                os.unlink(temp_log.name)
            
            return exit_code == 0, output
        finally:
            if os.path.exists(temp_script.name):
                os.unlink(temp_script.name)
    else:
        # Use full path to PowerShell with shell=True to properly inherit PATH
        args_str = f" {script_args}" if script_args else ""
        shell_cmd = f'"{POWERSHELL_PATH}" -ExecutionPolicy Bypass -File "{script_path}"{args_str}'
        logger.log(f"  Command: {shell_cmd}")
        try:
            result = subprocess.run(shell_cmd, capture_output=True, text=True, cwd=str(working_dir), shell=True)
            logger.log(f"  Exit code: {result.returncode}")
            return result.returncode == 0, result.stdout + result.stderr
        except FileNotFoundError as e:
            logger.log(f"  ERROR: FileNotFoundError - {e}", "ERROR")
            logger.log(f"  This usually means 'powershell' is not in PATH or the script file doesn't exist", "ERROR")
            raise
        except Exception as e:
            logger.log(f"  ERROR: {type(e).__name__} - {e}", "ERROR")
            raise


def run_deploy():
    """Run the deployment workflow."""
    # Initialize logging
    log_file = logger.initialize()
    logger.log(f"Script started from: {SCRIPT_DIR}")
    
    # Check for existing deployment
    state = None
    if has_previous_deployment():
        existing_state = load_state()
        completed = count_completed(existing_state)
        
        print(f"\n  {Colors.YELLOW}Previous deployment detected ({completed} steps completed).{Colors.RESET}")
        print(f"  {Colors.GRAY}Subscription: {existing_state['subscription_id']}{Colors.RESET}")
        print(f"  {Colors.GRAY}Location: {existing_state['location']}{Colors.RESET}")
        
        if confirm("Resume previous deployment?"):
            state = existing_state
            logger.log("Resuming previous deployment")
        elif not confirm("Start fresh deployment? (This will overwrite state)", default=False):
            print(f"\n{Colors.YELLOW}Exiting. No changes made.{Colors.RESET}")
            return 0
    
    # Configuration (not a numbered step)
    if state is None:
        print(f"\n{Colors.CYAN}=== Configuration ==={Colors.RESET}")
        
        # Get subscription ID
        subscription_id = prompt_input("Enter Azure Subscription ID", example="00000000-0000-0000-0000-000000000000")
        guid_pattern = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        while not re.match(guid_pattern, subscription_id):
            print(f"  {Colors.RED}Invalid subscription ID format. Please try again.{Colors.RESET}")
            subscription_id = prompt_input("Enter Azure Subscription ID", example="00000000-0000-0000-0000-000000000000")
        
        # Get location
        print(f"\n  {Colors.YELLOW}NOTE: Region must support both Availability Zones (required by VPN Gateway) AND AI Foundry Private subnet injection.{Colors.RESET}")
        print(f"  {Colors.YELLOW}      Supported regions: eastus, eastus2, westus3, westeurope, uksouth, swedencentral, australiaeast, japaneast, and others.{Colors.RESET}")
        print(f"  {Colors.YELLOW}      westus is NOT supported (no Availability Zones). eastus2 may have limited AI quota.{Colors.RESET}")
        location = prompt_input("Enter Azure Region", example="eastus, westus3, westeurope", default="eastus")
        
        # Deploy firewall?
        deploy_firewall = confirm("Deploy Azure Firewall? (~$900/month additional cost)", default=False)
        
        # Create state
        state = create_state(subscription_id, location, deploy_firewall)
        save_state(state)
        
        # Show summary
        sub_display = subscription_id
        try:
            sub_result = subprocess.run(
                f'az account show --subscription "{subscription_id}" --query "name" -o tsv',
                capture_output=True, text=True, timeout=10, shell=True
            )
            if sub_result.returncode == 0 and sub_result.stdout.strip():
                sub_display = f"{sub_result.stdout.strip()} ({subscription_id})"
        except Exception:
            pass

        print(f"\n  {Colors.GRAY}Deployment Configuration{Colors.RESET}")
        print(f"  {Colors.GRAY}------------------------{Colors.RESET}")
        print(f"  {Colors.GRAY}Subscription: {sub_display}{Colors.RESET}")
        print(f"  {Colors.GRAY}Location:     {location}{Colors.RESET}")
        print(f"  {Colors.GRAY}Firewall:     {'Yes' if deploy_firewall else 'No'}{Colors.RESET}")
        
        if not confirm("\n  Proceed with deployment?"):
            print(f"\n{Colors.YELLOW}Deployment cancelled.{Colors.RESET}")
            return 0
        
        print_result(True, "Configuration saved")
    
    # Step 1: Deploy Hub-Spoke Network
    if state["steps"]["hub_spoke"]["status"] != "completed":
        print_step(1, "Deploy Hub-Spoke Network (45-60 min)")
        print(f"  {Colors.GRAY}This step takes 45-60 minutes due to VPN Gateway provisioning.{Colors.RESET}")
        
        state = update_step(state, "hub_spoke", "in_progress")
        
        tf_vars = {
            "location": state["location"],
            "deploy_firewall": state["deploy_firewall"]
        }
        
        result = run_terraform(HUB_SPOKE_PATH, state["subscription_id"], tf_vars, log_file)
        
        if result["success"]:
            state = update_step(state, "hub_spoke", "completed")
            print_result(True, "Hub-Spoke network deployed")
            
            # Show resource info and save to state
            hub_info = get_hub_spoke_resource_info(state)
            vpn_name = get_terraform_output(HUB_SPOKE_PATH, "vpn_gateway_name")
            
            # Save resource names to state for destroy
            if "resources" not in state:
                state["resources"] = {}
            state["resources"]["hub_spoke_rg"] = hub_info["resource_group"]
            state["resources"]["vpn_gateway_name"] = vpn_name
            save_state(state)
            
            if hub_info["resource_group"]:
                rg_url = f"https://portal.azure.com/#@/resource/subscriptions/{state['subscription_id']}/resourceGroups/{hub_info['resource_group']}/overview"
                print(f"\n  {Colors.CYAN}Resource Group:{Colors.RESET} {hub_info['resource_group']}")
                print(f"  {Colors.CYAN}Azure Portal:{Colors.RESET} {rg_url}")
            if vpn_name:
                print(f"  {Colors.CYAN}VPN Gateway:{Colors.RESET} {vpn_name}")
                print(f"\n  {Colors.YELLOW}Note: After completing all steps, connect to VPN '{vpn_name}' to access resources.{Colors.RESET}")
        else:
            state = update_step(state, "hub_spoke", "failed")
            print_result(False, "Hub-Spoke deployment failed")
            logger.show_tail(20)
            
            if confirm("Retry this step?"):
                state = update_step(state, "hub_spoke", "pending")
                return run_deploy()
            else:
                print(f"\n{Colors.YELLOW}Deployment stopped. Run the script again to retry.{Colors.RESET}")
                return 1
    else:
        print_step(1, "Deploy Hub-Spoke Network")
        print_result(True, "Already completed (skipped)")
    
    # Step 2: Configure DNS Server
    if state["steps"]["dns_install"]["status"] != "completed":
        print_step(2, "Configure DNS Server")
        
        state = update_step(state, "dns_install", "in_progress")
        dns_script = SCRIPT_DIR / "hub-spoke-network" / "install-dns-server.ps1"
        
        # Get values from terraform state to pass as parameters (avoids PATH issues with terraform command)
        rg_name = get_terraform_output(HUB_SPOKE_PATH, "resource_group_name")
        vm_name = get_terraform_output(HUB_SPOKE_PATH, "dns_vm_name")
        
        print(f"  {Colors.GRAY}Installing DNS role and configuring forwarders...{Colors.RESET}")
        
        # Pass parameters directly to avoid terraform PATH issues in subprocess
        script_args = f'-ResourceGroupName "{rg_name}" -VMName "{vm_name}"' if rg_name and vm_name else None
        success, output = run_powershell_script(dns_script, script_args=script_args)
        
        _append_to_log(log_file, output)
        
        if success:
            state = update_step(state, "dns_install", "completed")
            print_result(True, "DNS Server configured")
        else:
            state = update_step(state, "dns_install", "failed")
            print_result(False, "DNS configuration failed")
            
            if confirm("Retry this step?"):
                state = update_step(state, "dns_install", "pending")
                return run_deploy()
    else:
        print_step(2, "Configure DNS Server")
        print_result(True, "Already completed (skipped)")
    
    # Step 3: Install VPN Certificates
    if state["steps"]["cert_install"]["status"] != "completed":
        print_step(3, "Install VPN Certificates")
        
        state = update_step(state, "cert_install", "in_progress")
        cert_script = SCRIPT_DIR / "hub-spoke-network" / "install-vpn-certs.ps1"
        
        print(f"  {Colors.YELLOW}Elevating to administrator for certificate installation...{Colors.RESET}")
        success, output = run_powershell_script(cert_script, elevated=True)
        
        _append_to_log(log_file, output)
        
        if success:
            state = update_step(state, "cert_install", "completed")
            print_result(True, "VPN certificates installed")
        else:
            state = update_step(state, "cert_install", "failed")
            print_result(False, "Certificate installation failed")
            
            if confirm("Retry this step?"):
                state = update_step(state, "cert_install", "pending")
                return run_deploy()
    else:
        print_step(3, "Install VPN Certificates")
        print_result(True, "Already completed (skipped)")
    
    # Step 4: Install VPN Client (optional but retryable)
    if state["steps"]["vpn_client"]["status"] not in ("completed", "skipped"):
        print_step(4, "Install VPN Client (Optional)")
        
        print(f"\n  {Colors.CYAN}Select VPN client type:{Colors.RESET}")
        print(f"    {Colors.YELLOW}[1]{Colors.RESET} Windows Native (IKEv2) - classic VPN client for x64/x86 systems")
        print(f"    {Colors.YELLOW}[2]{Colors.RESET} PowerShell VPN Connection  - recommended for ARM64 or if option 1 fails")
        print(f"    {Colors.YELLOW}[0]{Colors.RESET} Skip                    - install VPN client later manually")
        
        vpn_choice = input(f"\n  {Colors.YELLOW}-> Select option [0-2]: {Colors.RESET}").strip()
        
        if vpn_choice == "1":
            # Windows Native VPN Client
            state = update_step(state, "vpn_client", "in_progress")
            
            try:
                print(f"\n  {Colors.GRAY}Generating VPN client package...{Colors.RESET}")
                
                rg_name = get_terraform_output(HUB_SPOKE_PATH, "resource_group_name")
                vpn_gw_id = get_terraform_output(HUB_SPOKE_PATH, "vpn_gateway_id")
                vpn_gw_name = vpn_gw_id.split("/")[-1] if vpn_gw_id else None
                
                if not rg_name or not vpn_gw_name:
                    raise Exception(f"Could not get terraform outputs (rg={rg_name}, vpn={vpn_gw_name})")
                
                print(f"  {Colors.GRAY}  Resource Group: {rg_name}{Colors.RESET}")
                print(f"  {Colors.GRAY}  VPN Gateway: {vpn_gw_name}{Colors.RESET}")
                
                # Generate VPN client URL
                result = subprocess.run(
                    ["az", "network", "vnet-gateway", "vpn-client", "generate",
                     "--resource-group", rg_name, "--name", vpn_gw_name,
                     "--processor-architecture", "Amd64", "--output", "tsv"],
                    capture_output=True, text=True, shell=True
                )
                
                if result.returncode != 0:
                    raise Exception(f"Failed to generate VPN client: {result.stderr}")
                
                url = result.stdout.strip()
                if not url or not url.startswith("http"):
                    raise Exception(f"Invalid VPN client URL returned: {url}")
                
                print(f"  {Colors.GRAY}Downloading VPN client...{Colors.RESET}")
                vpn_zip = SCRIPT_DIR / "hub-spoke-network" / "VpnClient.zip"
                vpn_dir = SCRIPT_DIR / "hub-spoke-network" / "VpnClient"
                
                # Always remove stale VPN client files before extracting fresh config
                if vpn_dir.exists():
                    shutil.rmtree(vpn_dir, onerror=_remove_readonly)
                
                import urllib.request
                urllib.request.urlretrieve(url, vpn_zip)
                
                if not vpn_zip.exists():
                    raise Exception(f"Download failed - file not found: {vpn_zip}")
                
                print(f"  {Colors.GRAY}Extracting...{Colors.RESET}")
                import zipfile
                with zipfile.ZipFile(vpn_zip, "r") as zip_ref:
                    zip_ref.extractall(vpn_dir)
                
                # Check for installer
                installer = vpn_dir / "WindowsAmd64" / "VpnClientSetupAmd64.exe"
                if not installer.exists():
                    print(f"  {Colors.GRAY}Checking extracted contents...{Colors.RESET}")
                    for root, dirs, files in os.walk(vpn_dir):
                        for f in files:
                            print(f"    {Colors.GRAY}{os.path.join(root, f)}{Colors.RESET}")
                    raise Exception(f"Installer not found at: {installer}")
                
                print(f"  {Colors.GRAY}Launching installer (requires admin)...{Colors.RESET}")
                import tempfile
                temp_log = tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8')
                temp_log.close()
                
                temp_script = tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False, encoding='utf-8')
                temp_script.write(f'$ErrorActionPreference = "Continue"\n')
                temp_script.write(f'try {{\n')
                temp_script.write(f'    Start-Process -FilePath "{installer}" -Wait -PassThru | Out-Null\n')
                temp_script.write(f'    "VPN_INSTALL_SUCCESS" | Out-File -FilePath "{temp_log.name}" -Encoding utf8\n')
                temp_script.write(f'}} catch {{\n')
                temp_script.write(f'    $_.Exception.Message | Out-File -FilePath "{temp_log.name}" -Encoding utf8\n')
                temp_script.write(f'}}\n')
                temp_script.close()
                
                try:
                    result = subprocess.run(
                        [POWERSHELL_PATH, "-NoProfile", "-Command", 
                         f'Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "{temp_script.name}" -Wait'],
                        capture_output=True, text=True
                    )
                    
                    if result.stdout:
                        logger.log(f"VPN installer stdout: {result.stdout}", "INFO")
                    if result.stderr:
                        logger.log(f"VPN installer stderr: {result.stderr}", "INFO")
                    
                    vpn_result = ""
                    if os.path.exists(temp_log.name):
                        with open(temp_log.name, 'r', encoding='utf-8', errors='replace') as f:
                            vpn_result = f.read().strip()
                        logger.log(f"VPN installer result: {vpn_result}", "INFO")
                        os.unlink(temp_log.name)
                    
                finally:
                    if os.path.exists(temp_script.name):
                        os.unlink(temp_script.name)
                
                state = update_step(state, "vpn_client", "completed")
                print_result(True, "Windows Native VPN client installed")
                
            except Exception as e:
                state = update_step(state, "vpn_client", "failed")
                print_result(False, f"VPN client installation failed: {e}")
                logger.log(f"VPN client error: {e}", "ERROR")
                print(f"  {Colors.YELLOW}You can manually install later from: hub-spoke-network/VpnClient/WindowsAmd64/{Colors.RESET}")
                print(f"  {Colors.YELLOW}If you get 'custom script' errors, try option [2] Azure VPN Client instead.{Colors.RESET}")
                
                if confirm("Retry VPN client installation?"):
                    state = update_step(state, "vpn_client", "pending")
                    return run_deploy()
        
        elif vpn_choice == "2":
            # PowerShell VPN Connection (works on ARM64, no cmroute.dll needed)
            state = update_step(state, "vpn_client", "in_progress")
            
            try:
                print(f"\n  {Colors.GRAY}Downloading fresh VPN configuration from gateway...{Colors.RESET}")
                
                vpn_settings_file = SCRIPT_DIR / "hub-spoke-network" / "VpnClient" / "Generic" / "VpnSettings.xml"
                vpn_zip = SCRIPT_DIR / "hub-spoke-network" / "VpnClient.zip"
                vpn_dir = SCRIPT_DIR / "hub-spoke-network" / "VpnClient"
                
                # Always download fresh config from the gateway to avoid stale FQDN issues
                rg_name = get_terraform_output(HUB_SPOKE_PATH, "resource_group_name")
                vpn_gw_id = get_terraform_output(HUB_SPOKE_PATH, "vpn_gateway_id")
                vpn_gw_name = vpn_gw_id.split("/")[-1] if vpn_gw_id else None
                
                if not rg_name or not vpn_gw_name:
                    raise Exception(f"Could not get terraform outputs (rg={rg_name}, vpn={vpn_gw_name})")
                
                print(f"  {Colors.GRAY}  Resource Group: {rg_name}{Colors.RESET}")
                print(f"  {Colors.GRAY}  VPN Gateway: {vpn_gw_name}{Colors.RESET}")
                
                gen_result = subprocess.run(
                    ["az", "network", "vnet-gateway", "vpn-client", "generate",
                     "--resource-group", rg_name, "--name", vpn_gw_name,
                     "--processor-architecture", "Amd64", "--output", "tsv"],
                    capture_output=True, text=True, shell=True
                )
                
                if gen_result.returncode != 0:
                    raise Exception(f"Failed to generate VPN client: {gen_result.stderr}")
                
                url = gen_result.stdout.strip()
                if not url or not url.startswith("http"):
                    raise Exception(f"Invalid VPN client URL returned: {url}")
                
                # Remove stale VPN client files before extracting fresh config
                if vpn_dir.exists():
                    shutil.rmtree(vpn_dir, onerror=_remove_readonly)
                
                import urllib.request
                urllib.request.urlretrieve(url, vpn_zip)
                
                import zipfile
                with zipfile.ZipFile(vpn_zip, "r") as zip_ref:
                    zip_ref.extractall(vpn_dir)
                
                if not vpn_settings_file.exists():
                    raise Exception(f"VPN settings file not found after download: {vpn_settings_file}")
                
                # Parse VpnSettings.xml
                import xml.etree.ElementTree as ET
                tree = ET.parse(vpn_settings_file)
                root = tree.getroot()
                ns = {"": root.tag.split("}")[0] + "}" if "}" in root.tag else ""}
                
                vpn_server = root.find("VpnServer", ns)
                if vpn_server is None:
                    vpn_server = root.find("{http://www.w3.org/2001/XMLSchema-instance}VpnServer")
                if vpn_server is None:
                    # Try without namespace
                    for child in root:
                        if child.tag.endswith("VpnServer"):
                            vpn_server = child
                            break
                
                server_address = vpn_server.text if vpn_server is not None else None
                
                routes_elem = root.find("Routes") 
                if routes_elem is None:
                    for child in root:
                        if child.tag.endswith("Routes"):
                            routes_elem = child
                            break
                
                routes_text = routes_elem.text if routes_elem is not None else "10.0.0.0/16,10.1.0.0/16"
                
                vnet_name_elem = root.find("VnetName")
                if vnet_name_elem is None:
                    for child in root:
                        if child.tag.endswith("VnetName"):
                            vnet_name_elem = child
                            break
                
                connection_name = vnet_name_elem.text if vnet_name_elem is not None else "Azure-AI-Foundry-VPN"
                
                if not server_address:
                    raise Exception("Could not parse VPN server address from VpnSettings.xml")
                
                print(f"  {Colors.GRAY}  Server: {server_address}{Colors.RESET}")
                print(f"  {Colors.GRAY}  Connection: {connection_name}{Colors.RESET}")
                print(f"  {Colors.GRAY}  Routes: {routes_text}{Colors.RESET}")
                
                # Build route parameters for Add-VpnConnection
                routes = [r.strip() for r in routes_text.split(",")]
                route_cmds = "; ".join([
                    f'Add-VpnConnectionRoute -ConnectionName "{connection_name}" -DestinationPrefix "{route}" -PassThru'
                    for route in routes
                ])
                
                # EAP-TLS XML config for certificate-based authentication
                eap_tls_xml = (
                    '<EapHostConfig xmlns="http://www.microsoft.com/provisioning/EapHostConfig">'
                    '<EapMethod>'
                    '<Type xmlns="http://www.microsoft.com/provisioning/EapCommon">13</Type>'
                    '<VendorId xmlns="http://www.microsoft.com/provisioning/EapCommon">0</VendorId>'
                    '<VendorType xmlns="http://www.microsoft.com/provisioning/EapCommon">0</VendorType>'
                    '<AuthorId xmlns="http://www.microsoft.com/provisioning/EapCommon">0</AuthorId>'
                    '</EapMethod>'
                    '<Config xmlns="http://www.microsoft.com/provisioning/EapHostConfig">'
                    '<Eap xmlns="http://www.microsoft.com/provisioning/BaseEapConnectionPropertiesV1">'
                    '<Type>13</Type>'
                    '<EapType xmlns="http://www.microsoft.com/provisioning/EapTlsConnectionPropertiesV1">'
                    '<CredentialsSource><CertificateStore><SimpleCertSelection>true</SimpleCertSelection></CertificateStore></CredentialsSource>'
                    '<ServerValidation><DisableUserPromptForServerValidation>false</DisableUserPromptForServerValidation><ServerNames></ServerNames></ServerValidation>'
                    '<DifferentUsername>false</DifferentUsername>'
                    '<PerformServerValidation xmlns="http://www.microsoft.com/provisioning/EapTlsConnectionPropertiesV2">false</PerformServerValidation>'
                    '<AcceptServerName xmlns="http://www.microsoft.com/provisioning/EapTlsConnectionPropertiesV2">false</AcceptServerName>'
                    '</EapType></Eap></Config></EapHostConfig>'
                )
                
                # Create VPN connection via PowerShell with EAP-TLS certificate auth
                print(f"  {Colors.GRAY}Creating VPN connection...{Colors.RESET}")
                ps_script = (
                    f'Remove-VpnConnection -Name "{connection_name}" -Force -ErrorAction SilentlyContinue; '
                    f'$eapXml = \'{eap_tls_xml}\'; '
                    f'Add-VpnConnection -Name "{connection_name}" '
                    f'-ServerAddress "{server_address}" '
                    f'-TunnelType IKEv2 '
                    f'-AuthenticationMethod Eap '
                    f'-EapConfigXmlStream $eapXml '
                    f'-SplitTunneling '
                    f'-EncryptionLevel Required '
                    f'-RememberCredential; '
                    f'{route_cmds}; '
                    f'Write-Host "VPN connection created successfully"'
                )
                
                result = subprocess.run(
                    [POWERSHELL_PATH, "-NoProfile", "-Command", ps_script],
                    capture_output=True, text=True
                )
                
                if result.returncode != 0:
                    logger.log(f"VPN creation stderr: {result.stderr}", "ERROR")
                    raise Exception(f"Failed to create VPN connection: {result.stderr}")
                
                logger.log(f"VPN creation output: {result.stdout}", "INFO")
                
                print(f"\n  {Colors.GREEN}VPN connection '{connection_name}' created successfully.{Colors.RESET}")
                print(f"  {Colors.CYAN}To connect:{Colors.RESET}")
                print(f"    {Colors.GRAY}1. Open Windows Settings > Network & Internet > VPN{Colors.RESET}")
                print(f"    {Colors.GRAY}2. Click '{connection_name}' > Connect{Colors.RESET}")
                print(f"    {Colors.GRAY}   Or run: rasdial \"{connection_name}\"{Colors.RESET}")
                
                state = update_step(state, "vpn_client", "completed")
                print_result(True, "VPN connection created via PowerShell")
                
            except Exception as e:
                state = update_step(state, "vpn_client", "failed")
                print_result(False, f"VPN connection creation failed: {e}")
                logger.log(f"PowerShell VPN error: {e}", "ERROR")
                
                if confirm("Retry VPN client installation?"):
                    state = update_step(state, "vpn_client", "pending")
                    return run_deploy()
        
        else:
            state = update_step(state, "vpn_client", "skipped")
            print(f"  {Colors.YELLOW}VPN client skipped. Manual install instructions in README.{Colors.RESET}")
    else:
        print_step(4, "Install VPN Client (Optional)")
        print_result(True, "Already completed (skipped)")
    
    # Step 5: Deploy AI Foundry (BYO VNet or BYO VNet + APIM)
    print_step(5, "Deploy AI Foundry")

    if state["steps"]["byo_vnet"]["status"] != "completed":
        # Prompt for BYO/APIM only if not yet chosen (first run, after Reselect, or if user previously chose hub-spoke only)
        if not state.get("foundry_type") or state.get("foundry_type") == "none":
            print(f"\n  {Colors.CYAN}Choose your AI Foundry deployment option:{Colors.RESET}")
            print(f"    [1] AI Foundry (BYO VNet)         - Standard private network deployment (~20-30 min)")
            print(f"    [2] AI Foundry + APIM              - Adds API Management for controlled access (~45-60 min)")
            print(f"    [3] Hub-Spoke only                 - Deploy network infrastructure only, skip AI Foundry")
            while True:
                ft_choice = input(f"\n{Colors.YELLOW}  Select option [1/2/3]: {Colors.RESET}").strip()
                if ft_choice == "1":
                    state["foundry_type"] = "byo"
                    save_state(state)
                    break
                elif ft_choice == "2":
                    state["foundry_type"] = "apim"
                    save_state(state)
                    break
                elif ft_choice == "3":
                    state["foundry_type"] = "none"
                    save_state(state)
                    print(f"\n  {Colors.YELLOW}Skipping AI Foundry deployment. Hub-Spoke network is ready.{Colors.RESET}")
                    print_completion(log_file, state)
                    return 0
                else:
                    print(f"  {Colors.RED}Please enter 1, 2, or 3.{Colors.RESET}")

        foundry_label = get_foundry_label(state)
        tf_path = get_foundry_tf_path(state)

        if confirm(f"Deploy {foundry_label} resources?"):
            # Check and register required resource providers before deployment
            if not check_and_register_resource_providers(state):
                print(f"  {Colors.RED}Resource provider registration is required for AI Foundry deployment.{Colors.RESET}")
                if confirm("Skip deployment for now?"):
                    state = update_step(state, "byo_vnet", "skipped")
                    print(f"  {Colors.YELLOW}AI Foundry deployment skipped.{Colors.RESET}")
                    print_completion(log_file, state)
                    return 0
                return run_deploy()

            state = update_step(state, "byo_vnet", "in_progress")

            tf_vars = {
                "location": state["location"],
                "use_hub_spoke": True,
            }

            # For APIM deployments, populate publisher info from az account show
            if state.get("foundry_type") == "apim":
                try:
                    result = subprocess.run("az account show", capture_output=True, text=True, timeout=30, shell=True)
                    if result.returncode == 0:
                        account = json.loads(result.stdout)
                        user_name = account.get("user", {}).get("name", "AI Foundry Publisher")
                        # Use UPN as email if it looks like one, otherwise construct a placeholder
                        user_email = user_name if "@" in user_name else f"{user_name.replace(' ', '.').lower()}@example.com"
                        tf_vars["apim_publisher_name"] = user_name
                        tf_vars["apim_publisher_email"] = user_email
                        logger.log(f"APIM publisher set from account: name={user_name}, email={user_email}")
                except Exception as e:
                    logger.log(f"Could not get account info for APIM publisher: {e}", "WARNING")
                # Remove BYO-only var
                tf_vars.pop("use_hub_spoke", None)

            result = run_terraform(tf_path, state["subscription_id"], tf_vars, log_file)

            if result["success"]:
                state = update_step(state, "byo_vnet", "completed")
                print_result(True, f"{foundry_label} deployed")

                # Save resource names to state for destroy
                byo_info = get_byo_resource_info(state)
                foundry_name = get_terraform_output(tf_path, "ai_foundry_name")
                project_name = get_terraform_output(tf_path, "ai_foundry_project_name")
                rg_name = get_terraform_output(tf_path, "resource_group_name")

                if "resources" not in state:
                    state["resources"] = {}
                state["resources"]["byo_vnet_rg"] = rg_name or byo_info["resource_group"]
                state["resources"]["ai_foundry_name"] = foundry_name
                state["resources"]["ai_foundry_project_name"] = project_name
                save_state(state)
            else:
                state = update_step(state, "byo_vnet", "failed")
                print_result(False, f"{foundry_label} deployment failed")
                logger.show_tail(20)

                print(f"\n  {Colors.YELLOW}TIP: If this fails repeatedly, use the Destroy option (2) from the main menu{Colors.RESET}")
                print(f"  {Colors.YELLOW}     before retrying. Azure operations may be stuck and need cleanup.{Colors.RESET}")

                if confirm("Retry this step?"):
                    state = update_step(state, "byo_vnet", "pending")
                    return run_deploy()
        else:
            state = update_step(state, "byo_vnet", "skipped")
            print(f"  {Colors.YELLOW}AI Foundry deployment skipped.{Colors.RESET}")
    else:
        print_result(True, "Already completed (skipped)")
    
    # Completion
    print_completion(log_file, state)
    return 0


def main():
    """Main entry point with menu."""
    print_banner()
    
    # Start buffered logging for prerequisite checks (only written to file if checks fail)
    logger.start_buffering("prereq-check")
    logger.log(f"Current PATH: {os.environ.get('PATH', 'NOT SET')[:500]}...")  # Log first 500 chars of PATH
    
    # Refresh PATH from registry to pick up tools installed in previous sessions
    _refresh_path()
    logger.log("PATH refreshed from registry")
    
    # Check prerequisites once at startup
    print(f"\n{Colors.CYAN}Checking prerequisites...{Colors.RESET}")
    prereq_results = check_prerequisites()
    show_prerequisites(prereq_results)
    
    while not prereq_results["all_passed"]:
        # Flush buffered logs to file since prereqs failed
        logger.flush_buffer()
        print(f"  {Colors.GRAY}(Prereq check log: {logger.log_file}){Colors.RESET}")
        
        # Offer to install missing prerequisites
        if not handle_missing_prerequisites(prereq_results):
            print(f"\n{Colors.RED}Please install missing prerequisites and run again.{Colors.RESET}")
            return 1
        # If we get here, prerequisites were installed successfully
        print(f"\n{Colors.GREEN}Prerequisites installed successfully!{Colors.RESET}")
        # Re-check prerequisites
        print(f"\n{Colors.CYAN}Re-checking prerequisites...{Colors.RESET}")
        prereq_results = check_prerequisites()
        show_prerequisites(prereq_results)
    
    # All prerequisites passed - discard the buffer (no need to write log file)
    logger.discard_buffer()
    print(f"  {Colors.GREEN}All prerequisites verified!{Colors.RESET}")
    
    # Main menu loop
    while True:
        # Show main menu
        choice = show_main_menu()
        
        if choice == "deploy":
            result = run_deploy()
            if result != 0:
                return result
            # After successful deployment, show menu again
            input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "destroy":
            run_destroy()
        elif choice == "reset":
            run_reset()
        elif choice == "reselect_foundry":
            run_reselect_foundry()
        elif choice == "quit":
            print(f"\n{Colors.CYAN}Goodbye!{Colors.RESET}")
            return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Operation cancelled by user.{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        # Get full traceback for debugging
        tb_str = traceback.format_exc()
        print(f"\n{Colors.RED}FATAL ERROR: {e}{Colors.RESET}")
        print(f"{Colors.GRAY}Traceback:{Colors.RESET}")
        print(f"{Colors.GRAY}{tb_str}{Colors.RESET}")
        logger.log(f"Fatal error: {e}", "ERROR")
        logger.log(f"Traceback:\n{tb_str}", "ERROR")
        logger.show_tail(30)
        sys.exit(1)

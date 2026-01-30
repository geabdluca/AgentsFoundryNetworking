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
from datetime import datetime
from pathlib import Path

# Constants
SCRIPT_DIR = Path(__file__).parent.resolve()
STATE_FILE = SCRIPT_DIR / ".deployment-state.json"
LOG_DIR = SCRIPT_DIR / "logs"
HUB_SPOKE_PATH = SCRIPT_DIR / "hub-spoke-network" / "code"
BYO_VNET_PATH = SCRIPT_DIR / "byo-vnet" / "code"
VPN_CLIENT_PATH = SCRIPT_DIR / "VpnClient"
TOTAL_STEPS = 7


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
    
    def initialize(self, operation="deploy"):
        LOG_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        self.log_file = LOG_DIR / f"{operation}-{timestamp}.log"
        self.log(f"=== {operation.title()} Started ===")
        return self.log_file
    
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry + "\n")
    
    def show_tail(self, lines=20):
        if self.log_file and self.log_file.exists():
            print(f"\n{Colors.YELLOW}--- Last {lines} lines of log ---{Colors.RESET}")
            with open(self.log_file, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
                for line in all_lines[-lines:]:
                    print(f"{Colors.GRAY}{line.rstrip()}{Colors.RESET}")
            print(f"{Colors.YELLOW}--- Full log: {self.log_file} ---{Colors.RESET}\n")


logger = Logger()


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


def print_completion(log_path):
    """Display completion banner."""
    print(f"""
{Colors.GREEN}================================================================
  DEPLOYMENT COMPLETE
  
  Next Steps:
  1. Connect to VPN using Azure VPN Client
  2. Test DNS: nslookup <resource>.services.ai.azure.com
  3. Access AI Foundry: https://ai.azure.com
  
  Log file: {log_path}
================================================================{Colors.RESET}
""")


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
        
        print(f"  {Colors.GRAY}Running terraform destroy...{Colors.RESET}")
        result = subprocess.run(
            ["terraform", "destroy", "-auto-approve", "-no-color"],
            capture_output=True, text=True, env=env, timeout=1800  # 30 min timeout
        )
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(result.stdout + result.stderr)
        
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Terraform destroy timed out after 30 minutes"
    except Exception as e:
        return False, str(e)
    finally:
        os.chdir(original_dir)


def delete_resource_group(rg_name, subscription_id, log_file):
    """Delete an Azure resource group."""
    print(f"  {Colors.GRAY}Deleting resource group {rg_name}...{Colors.RESET}")
    
    result = subprocess.run(
        f'az group delete --name "{rg_name}" --subscription "{subscription_id}" --yes --no-wait --debug',
        capture_output=True, text=True, shell=True
    )
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"az group delete: {result.stdout} {result.stderr}\n")
    
    if result.returncode != 0:
        return False, result.stderr
    
    # Wait for deletion to complete
    print(f"  {Colors.GRAY}Waiting for resource group deletion...{Colors.RESET}")
    for i in range(60):  # Wait up to 10 minutes
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


def purge_cognitive_services(account_name, location, subscription_id, log_file):
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
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"Account {account_name} not found in deleted accounts after waiting, skipping purge\n")
        print(f"  {Colors.YELLOW}Account not found in deleted accounts after 2 minutes{Colors.RESET}")
        return True, "Account not in deleted state, skipping purge"
    
    print(f"  {Colors.GRAY}Account found, purging...{Colors.RESET}")
    
    # Purge the account
    result = subprocess.run(
        f'az cognitiveservices account purge --name "{account_name}" --resource-group "" --location "{location}" --subscription "{subscription_id}"',
        capture_output=True, text=True, shell=True
    )
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"az cognitiveservices purge: {result.stdout} {result.stderr}\n")
    
    if result.returncode != 0:
        # Try alternative approach - sometimes the RG is empty for deleted accounts
        result = subprocess.run(
            f'az resource delete --ids "/subscriptions/{subscription_id}/providers/Microsoft.CognitiveServices/locations/{location}/deletedAccounts/{account_name}" --debug',
            capture_output=True, text=True, shell=True
        )
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"az resource delete (purge): {result.stdout} {result.stderr}\n")
    
    return result.returncode == 0, result.stdout + result.stderr


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
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"Removed terraform state files: {removed}\n")
    
    return removed


def remove_vpn_client_files(log_file):
    """Remove downloaded VPN client files."""
    removed = []
    
    # Remove VpnClient directory in script root
    vpn_dir = SCRIPT_DIR / "VpnClient"
    if vpn_dir.exists():
        try:
            shutil.rmtree(vpn_dir)
            removed.append("VpnClient/")
        except Exception as e:
            logger.log(f"Failed to remove VpnClient: {e}", "WARNING")
    
    # Remove any downloaded zip files
    for zipfile in SCRIPT_DIR.glob("vpnclient*.zip"):
        try:
            zipfile.unlink()
            removed.append(zipfile.name)
        except Exception:
            pass
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"Removed VPN client files: {removed}\n")
    
    return removed


def remove_vpn_connection_profile(log_file):
    """Remove VPN connection profile from Windows."""
    # Get VPN connection names that match our pattern
    result = subprocess.run(
        ['powershell', '-NoProfile', '-Command', 
         'Get-VpnConnection | Where-Object { $_.Name -like "*hub*" -or $_.Name -like "*foundry*" -or $_.Name -like "*azure*" } | Select-Object -ExpandProperty Name'],
        capture_output=True, text=True
    )
    
    removed = []
    if result.returncode == 0 and result.stdout.strip():
        for vpn_name in result.stdout.strip().split('\n'):
            vpn_name = vpn_name.strip()
            if vpn_name:
                print(f"  {Colors.GRAY}Removing VPN connection: {vpn_name}{Colors.RESET}")
                del_result = subprocess.run(
                    ['powershell', '-NoProfile', '-Command',
                     f'Remove-VpnConnection -Name "{vpn_name}" -Force -ErrorAction SilentlyContinue'],
                    capture_output=True, text=True
                )
                if del_result.returncode == 0:
                    removed.append(vpn_name)
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"Removed VPN connections: {removed}\n")
    
    return removed


def get_byo_resource_info(state):
    """Get BYO VNet resource information from terraform state or output."""
    info = {
        "resource_group": "rg-aifoundry-resources",  # Default
        "ai_foundry_name": None,
        "location": state.get("location", "westus")
    }
    
    # Try to get from terraform output
    try:
        original_dir = os.getcwd()
        os.chdir(BYO_VNET_PATH)
        
        # Get AI Foundry name
        result = subprocess.run(
            ["terraform", "output", "-raw", "ai_foundry_name"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            info["ai_foundry_name"] = result.stdout.strip()
        
        # Get resource group name
        result = subprocess.run(
            ["terraform", "output", "-raw", "resource_group_name"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            info["resource_group"] = result.stdout.strip()
        
        os.chdir(original_dir)
    except Exception:
        pass
    
    return info


def get_hub_spoke_resource_info(state):
    """Get Hub-Spoke resource information from terraform state or output."""
    info = {
        "resource_group": None,
        "location": state.get("location", "westus")
    }
    
    # Try to get from terraform output
    try:
        original_dir = os.getcwd()
        os.chdir(HUB_SPOKE_PATH)
        
        result = subprocess.run(
            ["terraform", "output", "-raw", "resource_group_name"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            info["resource_group"] = result.stdout.strip()
        
        os.chdir(original_dir)
    except Exception:
        pass
    
    return info


def destroy_byo_vnet(state, log_file):
    """Destroy BYO VNet resources."""
    print(f"\n{Colors.CYAN}=== Destroying BYO VNet Resources ==={Colors.RESET}")
    logger.log("Starting BYO VNet destruction")
    
    byo_info = get_byo_resource_info(state)
    subscription_id = state["subscription_id"]
    
    # Step 1: Try terraform destroy
    print(f"\n{Colors.YELLOW}[1/4] Terraform Destroy{Colors.RESET}")
    tf_success, tf_output = run_terraform_destroy(BYO_VNET_PATH, subscription_id, log_file)
    
    if tf_success:
        print(f"  {Colors.GREEN}[OK] Terraform destroy completed{Colors.RESET}")
    else:
        print(f"  {Colors.YELLOW}[WARN] Terraform destroy failed, falling back to resource group deletion{Colors.RESET}")
        logger.log(f"Terraform destroy failed: {tf_output[:500]}", "WARNING")
        
        # Step 2: Fall back to RG deletion
        print(f"\n{Colors.YELLOW}[2/4] Delete Resource Group{Colors.RESET}")
        rg_success, rg_output = delete_resource_group(byo_info["resource_group"], subscription_id, log_file)
        
        if rg_success:
            print(f"  {Colors.GREEN}[OK] Resource group deleted{Colors.RESET}")
        else:
            print(f"  {Colors.RED}[FAIL] Resource group deletion failed: {rg_output}{Colors.RESET}")
            return False
    
    # Step 3: Purge cognitive services
    print(f"\n{Colors.YELLOW}[3/4] Purge Cognitive Services{Colors.RESET}")
    if byo_info["ai_foundry_name"]:
        purge_success, purge_output = purge_cognitive_services(
            byo_info["ai_foundry_name"], 
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
    
    # Step 4: Remove terraform state
    print(f"\n{Colors.YELLOW}[4/4] Clean Up Terraform State{Colors.RESET}")
    removed = remove_terraform_state(BYO_VNET_PATH, log_file)
    if removed:
        print(f"  {Colors.GREEN}[OK] Removed: {', '.join(removed)}{Colors.RESET}")
    else:
        print(f"  {Colors.GRAY}No state files to remove{Colors.RESET}")
    
    # Update state
    state = update_step(state, "byo_vnet", "pending")
    
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
    
    # Update state - reset all steps
    state = update_step(state, "hub_spoke", "pending")
    state = update_step(state, "dns_install", "pending")
    state = update_step(state, "cert_install", "pending")
    state = update_step(state, "vpn_client", "pending")
    
    print(f"\n{Colors.GREEN}Hub-Spoke destruction complete!{Colors.RESET}")
    logger.log("Hub-Spoke destruction completed")
    return True


def show_destroy_menu(state):
    """Show destroy options menu and return choice."""
    byo_status = state["steps"].get("byo_vnet", {}).get("status", "pending")
    hub_status = state["steps"].get("hub_spoke", {}).get("status", "pending")
    
    # Resources exist if completed, failed, or in_progress (partial deployment)
    byo_deployed = byo_status in ("completed", "failed", "in_progress")
    hub_deployed = hub_status in ("completed", "failed", "in_progress")
    
    print(f"\n{Colors.RED}=== Destroy Resources ==={Colors.RESET}")
    print(f"\n  Current deployment status:")
    print(f"    Hub-Spoke Network: {Colors.GREEN if hub_status == 'completed' else Colors.YELLOW if hub_status in ('failed', 'in_progress') else Colors.GRAY}{hub_status}{Colors.RESET}")
    print(f"    BYO VNet (AI Foundry): {Colors.GREEN if byo_status == 'completed' else Colors.YELLOW if byo_status in ('failed', 'in_progress') else Colors.GRAY}{byo_status}{Colors.RESET}")
    
    if not byo_deployed and not hub_deployed:
        print(f"\n  {Colors.YELLOW}No resources to destroy. All steps are pending.{Colors.RESET}")
        input(f"\n{Colors.GRAY}Press Enter to return to menu...{Colors.RESET}")
        return None
    
    print(f"\n  {Colors.YELLOW}Destroy Options:{Colors.RESET}")
    
    options = []
    if byo_deployed:
        options.append(("1", "Destroy BYO VNet only (AI Foundry resources)"))
    if byo_deployed or hub_deployed:
        options.append(("2", "Destroy ALL (BYO VNet + Hub-Spoke Network)"))
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
    
    print(f"\n{Colors.RED}{'='*60}")
    print(f"  WARNING: The following resources will be DESTROYED")
    print(f"{'='*60}{Colors.RESET}")
    
    if destroy_type in ("byo_only", "all"):
        print(f"\n  {Colors.YELLOW}BYO VNet (AI Foundry):{Colors.RESET}")
        print(f"    - Resource Group: {byo_info['resource_group']}")
        print(f"    - AI Foundry: {byo_info['ai_foundry_name'] or 'unknown'}")
        print(f"    - All resources in the group (Storage, CosmosDB, AI Search, etc.)")
    
    if destroy_type == "all":
        print(f"\n  {Colors.YELLOW}Hub-Spoke Network:{Colors.RESET}")
        print(f"    - Resource Group: {hub_info['resource_group'] or 'unknown'}")
        print(f"    - VPN Gateway, DNS VM, VNets, NSGs, etc.")
        print(f"    - VPN client files and connection profile")
    
    print(f"\n{Colors.RED}This action cannot be undone!{Colors.RESET}")
    
    confirm_text = "DESTROY"
    response = input(f"\n{Colors.YELLOW}Type '{confirm_text}' to confirm: {Colors.RESET}").strip()
    
    return response == confirm_text


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
                print(f"\n{Colors.YELLOW}Waiting 60 seconds before destroying Hub-Spoke...{Colors.RESET}")
                for i in range(6):
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
    
    print(f"\n{Colors.CYAN}=== Main Menu ==={Colors.RESET}")
    
    if has_deployment:
        completed = count_completed(state)
        print(f"\n  {Colors.GRAY}Previous deployment: {completed} steps completed{Colors.RESET}")
    
    print(f"\n  {Colors.YELLOW}Options:{Colors.RESET}")
    print(f"    [1] Deploy - Start or resume deployment")
    if has_destroyable:
        print(f"    [2] Destroy - Remove deployed resources")
    else:
        print(f"    {Colors.GRAY}[2] Destroy - No resources to destroy{Colors.RESET}")
    print(f"    [0] Quit")
    
    while True:
        choice = input(f"\n{Colors.YELLOW}  Select option: {Colors.RESET}").strip().lower()
        
        if choice == "1":
            return "deploy"
        elif choice == "2":
            if has_destroyable:
                return "destroy"
            else:
                print(f"  {Colors.YELLOW}No resources to destroy.{Colors.RESET}")
        elif choice == "0":
            return "quit"
        else:
            print(f"  {Colors.RED}Invalid option. Please try again.{Colors.RESET}")


# Prerequisites Check
def check_prerequisites():
    """Check if required tools are installed."""
    results = {"all_passed": True, "details": []}
    
    # Check Terraform
    tf_check = {"name": "Terraform", "installed": False, "version": None}
    try:
        result = subprocess.run(["terraform", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            match = re.search(r"Terraform v(\d+\.\d+\.\d+)", result.stdout)
            if match:
                tf_check["installed"] = True
                tf_check["version"] = match.group(1)
    except Exception:
        pass
    results["details"].append(tf_check)
    if not tf_check["installed"]:
        results["all_passed"] = False
    
    # Check Azure CLI (use shell=True on Windows because az is az.cmd)
    az_check = {"name": "Azure CLI", "installed": False, "version": None}
    try:
        result = subprocess.run("az --version", capture_output=True, text=True, timeout=10, shell=True)
        if result.returncode == 0:
            match = re.search(r"azure-cli\s+(\d+\.\d+\.\d+)", result.stdout)
            if match:
                az_check["installed"] = True
                az_check["version"] = match.group(1)
    except Exception:
        pass
    results["details"].append(az_check)
    if not az_check["installed"]:
        results["all_passed"] = False
    
    # Check Azure CLI login
    login_check = {"name": "Azure CLI Login", "installed": False, "version": None}
    try:
        result = subprocess.run("az account show", capture_output=True, text=True, timeout=10, shell=True)
        if result.returncode == 0:
            account = json.loads(result.stdout)
            login_check["installed"] = True
            login_check["version"] = f"Logged in as: {account.get('user', {}).get('name', 'unknown')}"
    except Exception:
        pass
    results["details"].append(login_check)
    if not login_check["installed"]:
        results["all_passed"] = False
    
    # Check OpenSSL (required for VPN certificate installation)
    openssl_check = {"name": "OpenSSL", "installed": False, "version": None}
    try:
        result = subprocess.run(["openssl", "version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            match = re.search(r"OpenSSL\s+([\d\.]+)", result.stdout)
            if match:
                openssl_check["installed"] = True
                openssl_check["version"] = match.group(1)
    except Exception:
        pass
    results["details"].append(openssl_check)
    if not openssl_check["installed"]:
        results["all_passed"] = False
    
    return results


def show_prerequisites(results):
    """Display prerequisites check results."""
    for check in results["details"]:
        if check["installed"]:
            version = f"- {check['version']}" if check["version"] else ""
            print(f"  {Colors.GREEN}[OK] {check['name']} {version}{Colors.RESET}")
        else:
            print(f"  {Colors.RED}[FAIL] {check['name']} - not found{Colors.RESET}")
    
    return results["all_passed"]


def get_missing_prerequisites(results):
    """Get list of missing prerequisites that can be auto-installed."""
    missing = []
    install_commands = {
        "Terraform": "Hashicorp.Terraform",
        "Azure CLI": "Microsoft.AzureCLI",
        "OpenSSL": "FireDaemon.OpenSSL",
    }
    
    for check in results["details"]:
        if not check["installed"] and check["name"] in install_commands:
            missing.append({
                "name": check["name"],
                "winget_id": install_commands[check["name"]]
            })
    
    return missing


def install_prerequisites(missing):
    """Install missing prerequisites using winget."""
    print(f"\n{Colors.CYAN}Installing missing prerequisites...{Colors.RESET}")
    
    for item in missing:
        print(f"\n  {Colors.YELLOW}Installing {item['name']}...{Colors.RESET}")
        print(f"  {Colors.GRAY}Running: winget install {item['winget_id']}{Colors.RESET}")
        
        result = subprocess.run(
            ["winget", "install", "--id", item["winget_id"], "--accept-source-agreements", "--accept-package-agreements"],
            capture_output=False,  # Show output to user
            text=True
        )
        
        if result.returncode == 0:
            print(f"  {Colors.GREEN}[OK] {item['name']} installed{Colors.RESET}")
        else:
            print(f"  {Colors.RED}[FAIL] {item['name']} installation failed{Colors.RESET}")
            print(f"  {Colors.YELLOW}Try manually: winget install {item['winget_id']}{Colors.RESET}")
    
    # Check if Azure CLI login is needed
    print(f"\n{Colors.GRAY}Re-checking prerequisites...{Colors.RESET}")


def handle_missing_prerequisites(results):
    """Handle missing prerequisites - offer to install or show manual instructions."""
    missing = get_missing_prerequisites(results)
    
    # Check if only login is missing
    login_missing = any(c["name"] == "Azure CLI Login" and not c["installed"] for c in results["details"])
    tools_missing = len(missing) > 0
    
    if tools_missing:
        print(f"\n{Colors.YELLOW}Missing tools can be installed automatically using winget.{Colors.RESET}")
        print(f"  Tools to install: {', '.join(m['name'] for m in missing)}")
        
        if confirm("\n  Install missing tools now?"):
            install_prerequisites(missing)
            
            # Re-check after installation
            new_results = check_prerequisites()
            show_prerequisites(new_results)
            
            if new_results["all_passed"]:
                return True
            
            # Check if only login is missing now
            login_missing = any(c["name"] == "Azure CLI Login" and not c["installed"] for c in new_results["details"])
            if login_missing and all(c["installed"] for c in new_results["details"] if c["name"] != "Azure CLI Login"):
                print(f"\n{Colors.YELLOW}Tools installed! Please run 'az login' to authenticate.{Colors.RESET}")
                return False
            
            print(f"\n{Colors.RED}Some prerequisites still missing after installation.{Colors.RESET}")
            return False
        else:
            print(f"\n{Colors.YELLOW}Manual installation commands:{Colors.RESET}")
            for m in missing:
                print(f"{Colors.GRAY}  winget install {m['winget_id']}{Colors.RESET}")
            if login_missing:
                print(f"{Colors.GRAY}  az login{Colors.RESET}")
            return False
    
    if login_missing:
        print(f"\n{Colors.YELLOW}Please run 'az login' to authenticate with Azure.{Colors.RESET}")
        return False
    
    return True


# Terraform Operations
def run_terraform(working_dir, subscription_id, variables, log_file, max_retries=2):
    """Run terraform init and apply with retry logic."""
    original_dir = os.getcwd()
    os.chdir(working_dir)
    
    try:
        # Set environment variable
        env = os.environ.copy()
        env["ARM_SUBSCRIPTION_ID"] = subscription_id
        
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
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(result.stdout + result.stderr)
        
        if result.returncode != 0:
            return {"success": False, "error": "Terraform init failed", "output": result.stderr}
        
        # Apply with retries
        for attempt in range(1, max_retries + 1):
            print(f"  {Colors.GRAY}Applying Terraform (attempt {attempt}/{max_retries})...{Colors.RESET}")
            
            result = subprocess.run(
                ["terraform", "apply", "-auto-approve", "-no-color"],
                capture_output=True, text=True, env=env
            )
            
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(result.stdout + result.stderr)
            
            if result.returncode == 0:
                return {"success": True, "output": result.stdout}
            
            if attempt < max_retries:
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


def get_terraform_output(working_dir, output_name):
    """Get a terraform output value."""
    original_dir = os.getcwd()
    os.chdir(working_dir)
    
    try:
        result = subprocess.run(
            ["terraform", "output", "-raw", output_name],
            capture_output=True, text=True
        )
        return result.stdout.strip() if result.returncode == 0 else None
    finally:
        os.chdir(original_dir)


def run_powershell_script(script_path, elevated=False, working_dir=None):
    """Run a PowerShell script from a specific directory."""
    script_path = Path(script_path).resolve()
    
    # Default working directory is the script's parent folder
    if working_dir is None:
        working_dir = script_path.parent
    
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
        temp_script.write(f'& "{script_path}" 2>&1 | Tee-Object -FilePath "{temp_log.name}"\n')
        temp_script.write(f'$exitCode = $LASTEXITCODE\n')
        temp_script.write(f'"EXIT_CODE:$exitCode" | Add-Content -Path "{temp_log.name}"\n')
        #temp_script.write(f'Read-Host "Press Enter to close..."\n')
        temp_script.close()
        
        try:
            cmd = [
                "powershell", "-Command",
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
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(working_dir))
        return result.returncode == 0, result.stdout + result.stderr


def run_deploy():
    """Run the deployment workflow."""
    # Initialize logging
    log_file = logger.initialize()
    logger.log(f"Script started from: {SCRIPT_DIR}")
    
    # Step 1: Prerequisites
    print_step(1, "Prerequisites Check")
    prereq_results = check_prerequisites()
    if not show_prerequisites(prereq_results):
        print(f"\n{Colors.RED}Please install missing prerequisites and run again.{Colors.RESET}")
        return 1
    print_result(True, "All prerequisites met")
    
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
    
    # Step 2: Configuration
    if state is None:
        print_step(2, "Configuration")
        
        # Get subscription ID
        subscription_id = prompt_input("Enter Azure Subscription ID", example="00000000-0000-0000-0000-000000000000")
        guid_pattern = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        while not re.match(guid_pattern, subscription_id):
            print(f"  {Colors.RED}Invalid subscription ID format. Please try again.{Colors.RESET}")
            subscription_id = prompt_input("Enter Azure Subscription ID", example="00000000-0000-0000-0000-000000000000")
        
        # Get location
        location = prompt_input("Enter Azure Region", example="eastus, westus2, westeurope", default="eastus")
        
        # Deploy firewall?
        deploy_firewall = confirm("Deploy Azure Firewall? (~$900/month additional cost)", default=False)
        
        # Create state
        state = create_state(subscription_id, location, deploy_firewall)
        save_state(state)
        
        # Show summary
        print(f"\n  {Colors.GRAY}Deployment Configuration{Colors.RESET}")
        print(f"  {Colors.GRAY}------------------------{Colors.RESET}")
        print(f"  {Colors.GRAY}Subscription: {subscription_id[:8]}...{Colors.RESET}")
        print(f"  {Colors.GRAY}Location:     {location}{Colors.RESET}")
        print(f"  {Colors.GRAY}Firewall:     {'Yes' if deploy_firewall else 'No'}{Colors.RESET}")
        
        if not confirm("\n  Proceed with deployment?"):
            print(f"\n{Colors.YELLOW}Deployment cancelled.{Colors.RESET}")
            return 0
        
        print_result(True, "Configuration saved")
    
    # Step 3: Deploy Hub-Spoke Network
    if state["steps"]["hub_spoke"]["status"] != "completed":
        print_step(3, "Deploy Hub-Spoke Network (45-60 min)")
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
        print_step(3, "Deploy Hub-Spoke Network")
        print_result(True, "Already completed (skipped)")
    
    # Step 4: Configure DNS Server
    if state["steps"]["dns_install"]["status"] != "completed":
        print_step(4, "Configure DNS Server")
        
        state = update_step(state, "dns_install", "in_progress")
        dns_script = SCRIPT_DIR / "hub-spoke-network" / "install-dns-server.ps1"
        
        print(f"  {Colors.GRAY}Installing DNS role and configuring forwarders...{Colors.RESET}")
        success, output = run_powershell_script(dns_script)
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(output)
        
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
        print_step(4, "Configure DNS Server")
        print_result(True, "Already completed (skipped)")
    
    # Step 5: Install VPN Certificates
    if state["steps"]["cert_install"]["status"] != "completed":
        print_step(5, "Install VPN Certificates")
        
        state = update_step(state, "cert_install", "in_progress")
        cert_script = SCRIPT_DIR / "hub-spoke-network" / "install-vpn-certs.ps1"
        
        print(f"  {Colors.YELLOW}Elevating to administrator for certificate installation...{Colors.RESET}")
        success, output = run_powershell_script(cert_script, elevated=True)
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(output)
        
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
        print_step(5, "Install VPN Certificates")
        print_result(True, "Already completed (skipped)")
    
    # Step 6: Install VPN Client (optional but retryable)
    if state["steps"]["vpn_client"]["status"] not in ("completed", "skipped"):
        print_step(6, "Install VPN Client (Optional)")
        
        if confirm("Download and install VPN client now?"):
            state = update_step(state, "vpn_client", "in_progress")
            
            try:
                print(f"  {Colors.GRAY}Generating VPN client package...{Colors.RESET}")
                
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
                    # Try alternate location
                    print(f"  {Colors.GRAY}Checking extracted contents...{Colors.RESET}")
                    for root, dirs, files in os.walk(vpn_dir):
                        for f in files:
                            print(f"    {Colors.GRAY}{os.path.join(root, f)}{Colors.RESET}")
                    raise Exception(f"Installer not found at: {installer}")
                
                print(f"  {Colors.GRAY}Launching installer (requires admin)...{Colors.RESET}")
                # Run installer with elevation
                subprocess.run(
                    ["powershell", "-Command", f"Start-Process '{installer}' -Verb RunAs -Wait"],
                    check=False
                )
                
                state = update_step(state, "vpn_client", "completed")
                print_result(True, "VPN client installed")
                
            except Exception as e:
                state = update_step(state, "vpn_client", "failed")
                print_result(False, f"VPN client installation failed: {e}")
                logger.log(f"VPN client error: {e}", "ERROR")
                print(f"  {Colors.YELLOW}You can manually install later from: hub-spoke-network/VpnClient/WindowsAmd64/{Colors.RESET}")
                
                if confirm("Retry VPN client installation?"):
                    state = update_step(state, "vpn_client", "pending")
                    return run_deploy()
        else:
            state = update_step(state, "vpn_client", "skipped")
            print(f"  {Colors.YELLOW}VPN client skipped. Manual install instructions in README.{Colors.RESET}")
    else:
        print_step(6, "Install VPN Client (Optional)")
        print_result(True, "Already completed (skipped)")
    
    # Step 7: Deploy BYO VNet AI Foundry
    print_step(7, "Deploy AI Foundry (BYO VNet)")
    
    if state["steps"]["byo_vnet"]["status"] != "completed":
        if confirm("Deploy BYO VNet AI Foundry resources? (20-30 min)"):
            state = update_step(state, "byo_vnet", "in_progress")
            
            tf_vars = {
                "location": state["location"],
                "use_hub_spoke": True
            }
            
            result = run_terraform(BYO_VNET_PATH, state["subscription_id"], tf_vars, log_file)
            
            if result["success"]:
                state = update_step(state, "byo_vnet", "completed")
                print_result(True, "AI Foundry deployed")
            else:
                state = update_step(state, "byo_vnet", "failed")
                print_result(False, "AI Foundry deployment failed")
                logger.show_tail(20)
                
                if confirm("Retry this step?"):
                    state = update_step(state, "byo_vnet", "pending")
                    return run_deploy()
        else:
            state = update_step(state, "byo_vnet", "skipped")
            print(f"  {Colors.YELLOW}AI Foundry deployment skipped.{Colors.RESET}")
    else:
        print_result(True, "Already completed (skipped)")
    
    # Completion
    print_completion(log_file)
    return 0


def main():
    """Main entry point with menu."""
    while True:
        print_banner()
        
        # Check prerequisites first
        print(f"\n{Colors.CYAN}Checking prerequisites...{Colors.RESET}")
        prereq_results = check_prerequisites()
        show_prerequisites(prereq_results)
        
        if not prereq_results["all_passed"]:
            # Offer to install missing prerequisites
            if not handle_missing_prerequisites(prereq_results):
                print(f"\n{Colors.RED}Please install missing prerequisites and run again.{Colors.RESET}")
                return 1
            # If we get here, prerequisites were installed successfully
            print(f"\n{Colors.GREEN}Prerequisites installed successfully!{Colors.RESET}")
            continue  # Re-check prerequisites
        
        print(f"  {Colors.GREEN}All prerequisites verified!{Colors.RESET}")
        
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
        print(f"\n{Colors.RED}FATAL ERROR: {e}{Colors.RESET}")
        logger.log(f"Fatal error: {e}", "ERROR")
        logger.show_tail(30)
        sys.exit(1)

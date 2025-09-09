export interface SubdomainConfig {
  subdomain: string;
  label: string;
}

export interface ServerAddressConfig {
  domain: string;
  subdomains: SubdomainConfig[];
}

// Default configuration - modify this to match your server setup
export const serverAddressConfig: ServerAddressConfig = {
  domain: "example.com",
  subdomains: [
    { subdomain: "*", label: "主地址" },
    { subdomain: "backup", label: "备用地址" },
    { subdomain: "de", label: "fzh地址" }
  ]
};

/**
 * Generate server address objects with address and label based on server ID and configuration
 */
export const generateServerAddresses = (serverId: string, config: ServerAddressConfig = serverAddressConfig): Array<{ address: string; label: string }> => {
  return config.subdomains.map(({ subdomain, label }) => {
    const address = subdomain === "*" 
      ? `${serverId}.${config.domain}`
      : `${serverId}.${subdomain}.${config.domain}`;
    
    return { address, label };
  });
};


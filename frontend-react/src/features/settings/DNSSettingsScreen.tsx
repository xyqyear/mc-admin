import { Plus, Trash2 } from 'lucide-react'
import { dnsSettings } from '@/features/settings/api'
import { useDNSSettingsSync } from '@/features/settings/commands'
import SettingsEditor, { SettingsSection } from '@/features/settings/ui/SettingsEditor'
import { BooleanField, FormField, NumberField, TextField } from '@/shared/components/FormFields'
import { Button } from '@/shared/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/ui/select'

export default function DNSSettingsScreen() {
  const sync = useDNSSettingsSync()
  return <SettingsEditor title="DNS 设置" resource={dnsSettings} afterSave={sync}>{(value, update) => {
    const provider = value.dns
    return <>
      <SettingsSection title="DNS 服务">
        <BooleanField label="启用 DNS 管理" value={value.enabled} onChange={enabled => update({ ...value, enabled })} />
        <FormField label="DNS 提供商">{id => <Select value={provider.type} onValueChange={type => {
          if (type === 'huawei') update({ ...value, dns: { type, domain: provider.domain, ak: '', sk: '', region: 'cn-south-1' } })
          if (type === 'dnspod') update({ ...value, dns: { type, domain: provider.domain, id: '', key: '' } })
        }} itemToStringLabel={type => type === 'huawei' ? '华为云 DNS' : 'DNSPod'}>
          <SelectTrigger id={id}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="huawei">华为云 DNS</SelectItem><SelectItem value="dnspod">DNSPod</SelectItem></SelectContent>
        </Select>}</FormField>
        <TextField label="域名" value={provider.domain} onChange={domain => update({ ...value, dns: { ...provider, domain } })} required={value.enabled} />
        {provider.type === 'huawei' ? <>
          <TextField label="访问密钥 ID" value={provider.ak} onChange={ak => update({ ...value, dns: { ...provider, ak } })} required={value.enabled} />
          <TextField label="秘密访问密钥" type="password" value={provider.sk} onChange={sk => update({ ...value, dns: { ...provider, sk } })} required={value.enabled} autoComplete="off" />
          <TextField label="DNS 区域" value={provider.region} onChange={region => update({ ...value, dns: { ...provider, region } })} required={value.enabled} />
        </> : <>
          <TextField label="DNSPod API 标识" value={provider.id} onChange={id => update({ ...value, dns: { ...provider, id } })} required={value.enabled} />
          <TextField label="DNSPod API 密钥" type="password" value={provider.key} onChange={key => update({ ...value, dns: { ...provider, key } })} required={value.enabled} autoComplete="off" />
        </>}
        <TextField label="托管子域名" value={value.managed_sub_domain} onChange={managed_sub_domain => update({ ...value, managed_sub_domain })} />
        <TextField label="mc-router 基础 URL" value={value.mc_router_base_url} onChange={mc_router_base_url => update({ ...value, mc_router_base_url })} />
        <NumberField label="DNS TTL" value={value.dns_ttl} onChange={dns_ttl => update({ ...value, dns_ttl: dns_ttl ?? NaN })} step={1} required />
      </SettingsSection>
      <SettingsSection title="手动地址">
        {value.addresses.map((address, index) => {
          const change = (next: typeof address) => update({ ...value, addresses: value.addresses.map((entry, i) => i === index ? next : entry) })
          return <div key={index} className="rounded-lg border p-4 space-y-4">
            <TextField label={`地址名称 ${index + 1}`} value={address.name} onChange={name => change({ ...address, name })} />
            <FormField label={`记录类型 ${index + 1}`}>{id => <Select value={address.record_type} onValueChange={record_type => { if (record_type) change({ ...address, record_type }) }}><SelectTrigger id={id}><SelectValue /></SelectTrigger><SelectContent>{(['A', 'AAAA', 'CNAME'] as const).map(type => <SelectItem key={type} value={type}>{type}</SelectItem>)}</SelectContent></Select>}</FormField>
            <TextField label={`记录值 ${index + 1}`} value={address.value} onChange={text => change({ ...address, value: text })} />
            <NumberField label={`端口 ${index + 1}`} value={address.port} onChange={port => change({ ...address, port: port ?? NaN })} step={1} required />
            <Button type="button" variant="outline" onClick={() => update({ ...value, addresses: value.addresses.filter((_, i) => i !== index) })}><Trash2 />删除地址 {index + 1}</Button>
          </div>
        })}
        <Button type="button" variant="outline" onClick={() => update({ ...value, addresses: [...value.addresses, { type: 'manual', name: '', record_type: 'A', value: '', port: 25565 }] })}><Plus />添加地址</Button>
      </SettingsSection>
    </>
  }}</SettingsEditor>
}

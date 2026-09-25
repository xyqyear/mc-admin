package dns

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"math/big"
	"os"
	"path/filepath"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/fixtures"
	"mc-admin/e2e/internal/platform"
)

// Only the owned deployment trusts this certificate and resolves the provider to loopback.
func startOwnedDNSEdge(ctx context.Context, t *engine.Scope) error {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		return err
	}
	serial, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if err != nil {
		return err
	}
	certificate := &x509.Certificate{SerialNumber: serial, Subject: pkix.Name{CommonName: "MC Admin owned DNS edge"}, DNSNames: []string{"dnspod.tencentcloudapi.com"}, NotBefore: time.Now().Add(-time.Minute), NotAfter: time.Now().Add(24 * time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	der, err := x509.CreateCertificate(rand.Reader, certificate, certificate, &key.PublicKey, key)
	if err != nil {
		return err
	}
	files := map[string][]byte{
		"dns-edge.pem":     pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}),
		"dns-edge-key.pem": pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key)}),
		"dns-edge.py":      []byte(ownedDNSEdge), "dns-edge-control.py": []byte(ownedDNSEdgeControl),
	}
	for name, data := range files {
		if err := os.WriteFile(filepath.Join(t.Env.Dir, name), data, 0600); err != nil {
			return err
		}
	}
	backend := fixtures.BackendOf(t.Env)
	const trust = `import certifi,pathlib
certificate=pathlib.Path('/data/dns-edge.pem').read_bytes()
with pathlib.Path(certifi.where()).open('ab') as stream: stream.write(b'\n'+certificate)
with pathlib.Path('/etc/hosts').open('a') as stream: stream.write('\n127.0.0.1 dnspod.tencentcloudapi.com\n')
`
	if _, err = backend.Docker.Run(ctx, "exec", backend.Name, "python", "-c", trust); err != nil {
		return err
	}
	journal := environment.Get[*platform.Journal](t.Env, "journal")
	name := "mca-e2e-" + t.Env.ID + "-dns-edge"
	if err = journal.Track(t.Env.ID, name, ""); err != nil {
		return err
	}
	options := environment.Get[fixtures.Options](t.Env, "options")
	if _, err = backend.Docker.Run(ctx, "run", "-d", "--name", name, "--network", "container:"+backend.Name, "--label", platform.RunLabel+"="+journal.Manifest.RunID, "--label", platform.EnvLabel+"="+t.Env.ID, "--mount", "type=bind,src="+t.Env.Dir+",dst=/data,readonly", "--entrypoint", "python", options.Image, "/data/dns-edge.py"); err != nil {
		return err
	}
	return api.Wait(ctx, 200*time.Millisecond, "owned DNS TLS edge readiness", func(ctx context.Context) (bool, error) { _, err := edgeControl(ctx, t, nil); return err == nil, err })
}

type edgeState struct {
	Records []map[string]any `json:"records"`
	Calls   []map[string]any `json:"calls"`
}

func edgeControl(ctx context.Context, t *engine.Scope, change map[string]any) (edgeState, error) {
	payload, err := json.Marshal(change)
	if err != nil {
		return edgeState{}, err
	}
	backend := fixtures.BackendOf(t.Env)
	output, err := backend.Docker.Run(ctx, "exec", backend.Name, "python", "/data/dns-edge-control.py", string(payload))
	if err != nil {
		return edgeState{}, err
	}
	var state edgeState
	if err = json.Unmarshal([]byte(output), &state); err != nil {
		return state, fmt.Errorf("decode DNS edge: %w", err)
	}
	t.Recorder.Event("dns_owned_edge", map[string]any{"change": change, "state": state})
	return state, nil
}

const ownedDNSEdgeControl = `import json,sys,urllib.request
body=json.loads(sys.argv[1])
request=urllib.request.Request('http://127.0.0.1:26668/',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(request,timeout=10) as response: print(response.read().decode())
`

const ownedDNSEdge = `import http.server,json,ssl,threading,urllib.request,urllib.error
lock=threading.RLock()
state={'records':[],'calls':[],'dns_read_failure':False,'router_read_failure':False,'fail_name':None,'next_id':1}
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def body(self): return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'null')
 def respond(self,status,body):
  data=json.dumps(body).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_POST(self):
  body=self.body()
  with lock:
   if self.server.server_port==26668:
    if body:
     if body.pop('clear_calls',False):state['calls']=[]
     state.update(body)
    return self.respond(200,{'records':state['records'],'calls':state['calls']})
   if self.server.server_port==26667:return self.route('POST',body)
   action=self.headers.get('X-TC-Action')
   result={'RequestId':'owned-e2e-request'}
   if state['dns_read_failure'] and action in ('DescribeDomainList','DescribeRecordList'):
    result['Error']={'Code':'InternalError','Message':'synthetic-dns-edge-secret'}
   elif action=='DescribeDomainList':result['DomainList']=[{'Name':'e2e.invalid','DomainId':1}]
   elif action=='DescribeRecordList':result['RecordList']=state['records']
   elif action=='CreateRecordBatch':
    for record in body['RecordList']:
     state['calls'].append({'target':'dns','action':action,'name':record['SubDomain']})
     if state['fail_name']==record['SubDomain']:
      result['Error']={'Code':'InternalError','Message':'synthetic-dns-edge-secret'};break
     state['records'].append({'Name':record['SubDomain'],'RecordId':state['next_id'],'Type':record['RecordType'],'Value':record['Value'],'TTL':record['TTL']});state['next_id']+=1
    result['JobId']=1;result['DetailList']=[]
   elif action=='DeleteRecordBatch':
    state['calls'].append({'target':'dns','action':action,'ids':body['RecordIdList']})
    state['records']=[r for r in state['records'] if r['RecordId'] not in body['RecordIdList']];result['JobId']=1
   else:result['Error']={'Code':'InvalidAction','Message':'unsupported owned fixture request'}
   return self.respond(200,{'Response':result})
 def do_GET(self):
  with lock:return self.route('GET',None)
 def do_DELETE(self):
  with lock:return self.route('DELETE',None)
 def route(self,method,body):
  if self.server.server_port!=26667:return self.respond(404,{})
  if method=='GET' and state['router_read_failure']:return self.respond(503,{'error':'synthetic-dns-edge-secret'})
  if method!='GET':state['calls'].append({'target':'router','action':method,'path':self.path,'body':body})
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  request=urllib.request.Request('http://127.0.0.1:26666'+self.path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
  try:
   with opener.open(request,timeout=10) as response:return self.respond(response.status,json.loads(response.read() or b'{}'))
  except urllib.error.HTTPError as error:return self.respond(error.code,{'error':'owned router HTTP failure'})
servers=[]
for port in (443,26667,26668):
 server=http.server.ThreadingHTTPServer(('127.0.0.1',port),Handler)
 if port==443:
  tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain('/data/dns-edge.pem','/data/dns-edge-key.pem');server.socket=tls.wrap_socket(server.socket,server_side=True)
 servers.append(server);threading.Thread(target=server.serve_forever,daemon=True).start()
threading.Event().wait()
`

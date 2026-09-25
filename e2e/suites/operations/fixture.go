package operations

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/fixtures"
	"mc-admin/e2e/internal/platform"
)

type interruptedInput struct {
	ID                   string `json:"id"`
	Kind                 string `json:"kind"`
	Origin               string `json:"origin"`
	ServerID             string `json:"server_id"`
	Resource             string `json:"resource"`
	ConfigurationVersion string `json:"configuration_version,omitempty"`
	CronjobID            string `json:"cronjob_id,omitempty"`
	Changed              bool   `json:"changed"`
}

func prepareInterruptedHistory(ctx context.Context, t *engine.Scope, inputs []interruptedInput) error {
	backend := fixtures.BackendOf(t.Env)
	if _, err := backend.Docker.Run(ctx, "stop", "--time", "10", backend.Name); err != nil {
		return err
	}
	payload, err := json.Marshal(inputs)
	if err != nil {
		return err
	}
	const seed = `import datetime,json,sqlite3,sys
db=sqlite3.connect('/data/db.sqlite3')
now=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=1)
for item in json.loads(sys.argv[1]):
 server=db.execute("SELECT id FROM server WHERE server_id=? AND status='ACTIVE'",(item['server_id'],)).fetchone()
 if server is None: raise RuntimeError('fixture requires an API-created active server')
 resource={'kind':item['resource'],'server_id':item['server_id'],'generation':server[0],'path':''}
 row={'operation_id':item['id'],'kind':item['kind'],'actor_id':None,'origin':item['origin'],'name':'E2E interrupted operation','legacy_id':item['id'],'running_intent':False,'configuration_version':item.get('configuration_version'),'resources_json':json.dumps([resource]),'state':'running','phase':'fixture_write_started','created_at':now.isoformat(),'updated_at':now.isoformat(),'ended_at':None,'data_changed':item['changed'],'writers_stopped':False,'ownership_known':True,'processes_json':'[]','recovery_refs_json':'[]','has_recovery_refs':False,'failure_code':None,'blocked_reason':None,'cache_degraded':False,'resolved_by':None,'resolved_at':None}
 keys=list(row)
 db.execute('INSERT INTO operation_journal ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',[row[key] for key in keys])
 if item.get('cronjob_id'):
  db.execute('INSERT INTO cronjob_execution (cronjob_id,execution_id,started_at,ended_at,duration_ms,status,messages_json) VALUES (?,?,?,NULL,NULL,?,?)',(item['cronjob_id'],item['id'],now.isoformat(),'RUNNING','["E2E interrupted before completion"]'))
db.commit()
db.close()
`
	_, err = fixtures.DeploymentCommand(ctx, t.Env, "interrupted-history-input", "python", "-c", seed, string(payload))
	if err == nil {
		t.Recorder.Event("interrupted_history_fixture", map[string]any{"inputs": inputs, "processes": "none; stopped deployment"})
	}
	return err
}

func loadOperation(ctx context.Context, client *api.Client, id string) (operation, error) {
	var result operation
	err := client.JSON(ctx, "GET", "/api/operations/"+id, nil, &result, 200)
	return result, err
}

func interrupted(result operation, id, serverID string) error {
	if result.ID != id || result.State != "interrupted" || result.Phase != "fixture_write_started" || !result.WritersStopped || result.Ended == nil || result.Ended.Before(result.Created) {
		return fmt.Errorf("operation did not retain an interrupted terminal result: %+v", result)
	}
	if len(result.Resources) != 1 || result.Resources[0].ServerID != serverID || result.Resources[0].Generation <= 0 {
		return fmt.Errorf("operation lost its exact server reference: %+v", result.Resources)
	}
	return nil
}

func createIndependentServer(ctx context.Context, t *engine.Scope, client *api.Client) (string, error) {
	journal := environment.Get[*platform.Journal](t.Env, "journal")
	options := environment.Get[fixtures.Options](t.Env, "options")
	ports, err := platform.LeasePorts(ctx, journal.Docker, options.PortDirectory, 2)
	if err != nil {
		return "", err
	}
	t.Cleanup(func(context.Context) error { return ports.Close() })
	id := fixtures.ServerOf(t.Env).ID + "-independent"
	if err = journal.Track(t.Env.ID, "mc-"+id, "e2e-"+t.Env.ID); err != nil {
		return "", err
	}
	compose := fixtures.Compose(t.Env, id, fmt.Sprint(ports.Ports[0]), fmt.Sprint(ports.Ports[1]))
	if err = client.JSON(ctx, "POST", "/api/servers/"+id, map[string]string{"yaml_content": compose}, nil, 200); err != nil {
		return "", err
	}
	return id, nil
}

func replaceOwnedCompose(t *engine.Scope, content string) error {
	project := filepath.Join(t.Env.Dir, "servers", fixtures.ServerOf(t.Env).ID)
	temporary := filepath.Join(project, "recovery-compose.tmp")
	if err := os.WriteFile(temporary, []byte(content), 0600); err != nil {
		return err
	}
	return os.Rename(temporary, filepath.Join(project, "docker-compose.yml"))
}

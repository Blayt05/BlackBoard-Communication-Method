using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.Networking;

public class ObjectAgent : MonoBehaviour
{
    public string agentId;
    private NavMeshAgent navMesh;

    // Carrying
    public bool beingCarried = false;
    public Transform carrier;

    // If I'm an agent, reference to the box I'm carrying
    private ObjectAgent carriedBox = null;
    private Vector3 pickupPosition;
    private float pickupTimestamp = 0f;
    public float minCarryDistance = 0.6f;
    public float minCarryDelay = 0.15f;

    // Stuck detection
    private Vector3 lastPos;
    private float stuckTimer = 0f;
    public float stuckCheckInterval = 0.5f;    // cada cuánto comprobamos
    public float stuckMoveThreshold = 0.05f;   // si no se movió más que esto -> se considera atascado
    public float stuckTimeThreshold = 1.2f;    // tiempo acumulado para considerar stuck
    private float stuckCheckAccumulator = 0f;

    // Detour (legacy flags kept minimal)
    private bool isDetouring = false;
    private Vector3 detourTarget;
    private float detourTimeout = 2.0f;        // cuánto intentamos el detour antes de resetear
    private float detourTimer = 0f;

    // Obstacle reference (for boxes)
    private NavMeshObstacle myObstacle;

    // init flag
    private bool initializedPos = false;

    // Recovery parameters (ajustables en inspector)
    public float backupDistance = 0.6f;        // cuánto retroceder en el primer intento
    public float backupTimeout = 0.6f;         // tiempo para el backup
    public float turnRadius = 0.6f;            // distancia para probar giro lateral
    public int detourAttempts = 3;             // cuántos detours intentar
    public float detourRadius = 1.8f;          // radio para samplear detour puntos
    public float detourTimeoutPublic = 1.6f;   // tiempo para intentar cada detour
    public float yieldDuration = 0.45f;        // tiempo para dejar pasar a otros agentes
    public int maxRecoveryRetries = 2;         // cuántas veces repetir la secuencia total
    private bool isRecovering = false;         // flag para evitar corutinas superpuestas

    // Negotiation parameters
    public float negotiationRadius = 0.9f;     // radio para detectar agentes cercanos
    public float negotiationDistanceThreshold = 0.45f; // distancia límite para negociar
    public LayerMask agentLayer;               // layer usado para los agentes (configurar en inspector)

    void Awake() {
        navMesh = GetComponent<NavMeshAgent>();
        myObstacle = GetComponent<NavMeshObstacle>();
        if (navMesh == null && IsAgent()) {
            navMesh = gameObject.AddComponent<NavMeshAgent>();
        }

        // Randomize avoidance priority to reduce symmetry deadlocks
        if (navMesh != null) {
            navMesh.avoidancePriority = Random.Range(0, 100);
        }
    }

    void Start() {
        lastPos = transform.position;
    }

    private bool IsAgent() {
        return !string.IsNullOrEmpty(agentId) && agentId.StartsWith("Agent");
    }

    public void SyncPosition(Vector3 pos) {
        if (string.IsNullOrEmpty(agentId)) return;

        if (agentId.StartsWith("Box")) {
            if (beingCarried && carrier != null) {
                transform.position = carrier.position + Vector3.up * 0.45f;
            } else {
                if (!initializedPos) {
                    transform.position = pos;
                    initializedPos = true;
                }
            }
        } else {
            if (navMesh != null && navMesh.isOnNavMesh) {
                navMesh.SetDestination(pos);
            } else {
                transform.position = pos;
            }
        }
    }

    void OnTriggerEnter(Collider other) {
        if (!IsAgent()) return;

        if (other.CompareTag("Box")) {
            var boxAgent = other.GetComponent<ObjectAgent>();
            if (boxAgent != null && !boxAgent.beingCarried) {
                Debug.Log($"{agentId} pickup {other.gameObject.name}");
                boxAgent.beingCarried = true;
                boxAgent.carrier = this.transform;
                this.carriedBox = boxAgent;
                pickupPosition = transform.position;
                pickupTimestamp = Time.time;

                // disable carving while moving box (evita recalculos conflictivos)
                var obst = other.GetComponent<NavMeshObstacle>();
                if (obst != null) obst.enabled = false;

                StartCoroutine(PostPickup(agentId, other.gameObject.name));
            }
        }
    }

    void Update() {
        // Local negotiation: si estamos muy cerca de otro agente, decidir quien cede
        if (IsAgent()) {
            HandleLocalNegotiation();
        }

        // STUCK DETECTION (solo para agents)
        if (IsAgent() && navMesh != null && navMesh.hasPath) {
            stuckCheckAccumulator += Time.deltaTime;
            if (stuckCheckAccumulator >= stuckCheckInterval) {
                float moved = Vector3.Distance(transform.position, lastPos);
                if (moved <= stuckMoveThreshold) {
                    stuckTimer += stuckCheckAccumulator;
                } else {
                    stuckTimer = 0f;
                }
                lastPos = transform.position;
                stuckCheckAccumulator = 0f;
            }

            if (stuckTimer >= stuckTimeThreshold) {
                Debug.LogWarning($"{agentId} parece atascado (stuckTimer={stuckTimer:F2}). Intentando recovery...");
                TryRecovery();
                stuckTimer = 0f;
            }
        }

        // DETOUR HANDLING (legacy, preservado)
        if (isDetouring) {
            detourTimer += Time.deltaTime;
            if (detourTimer >= detourTimeout) {
                Debug.Log($"{agentId} detour timeout, reset path");
                isDetouring = false;
                detourTimer = 0f;
                if (navMesh != null) navMesh.ResetPath();
            }
        }

        // Carry/drop logic
        if (IsAgent() && navMesh != null && carriedBox != null && !navMesh.pathPending) {
            if (navMesh.remainingDistance <= navMesh.stoppingDistance) {
                float moved = Vector3.Distance(pickupPosition, transform.position);
                float elapsed = Time.time - pickupTimestamp;
                if (elapsed >= minCarryDelay || moved >= minCarryDistance) {
                    Debug.Log($"{agentId} drop {carriedBox.gameObject.name} (moved {moved:F2} elapsed {elapsed:F2})");
                    // soltar local
                    carriedBox.beingCarried = false;
                    carriedBox.carrier = null;
                    // reenable obstacle siguiente frame
                    var obst = carriedBox.GetComponent<NavMeshObstacle>();
                    if (obst != null) StartCoroutine(ReenableObstacleNextFrame(obst));
                    Vector3 finalPos = carriedBox.transform.position;
                    string boxIdName = carriedBox.gameObject.name;
                    StartCoroutine(PostDrop(agentId, boxIdName, finalPos));
                    carriedBox = null;
                }
            }
        }
    }

    // Negotiation: si estoy muy cerca de otro agente, el de menor prioridad cede con BriefYield()
    void HandleLocalNegotiation() {
        if (navMesh == null) return;
        // Detect nearby agents using layer mask
        Collider[] hits = Physics.OverlapSphere(transform.position, negotiationRadius, agentLayer);
        foreach (var h in hits) {
            if (h.gameObject == this.gameObject) continue;
            ObjectAgent other = h.GetComponent<ObjectAgent>();
            if (other == null) continue;
            // solo negociar si ambos tienen NavMeshAgent
            var theirNav = other.navMesh;
            if (theirNav == null) continue;

            float dist = Vector3.Distance(transform.position, other.transform.position);
            if (dist < negotiationDistanceThreshold) {
                int myPriority = navMesh != null ? navMesh.avoidancePriority : 50;
                int theirPriority = theirNav != null ? theirNav.avoidancePriority : 50;

                // Si mi prioridad es menor o igual, yo cedo (hago brief yield)
                if (myPriority <= theirPriority) {
                    if (!isRecovering) {
                        Debug.Log($"{agentId} cede a {other.agentId} (myP={myPriority} theirP={theirPriority}) -> BriefYield()");
                        StartCoroutine(BriefYield());
                    }
                    // Si cedo, no necesito revisar otros vecinos ahora
                    return;
                } else {
                    // Yo tengo mayor prioridad, no cedo.
                    // en este caso el otro agente debería ceder cuando evalúe su HandleLocalNegotiation
                }
            }
        }
    }

    IEnumerator ReenableObstacleNextFrame(NavMeshObstacle o) {
        yield return null;
        o.enabled = true;
    }

    // ---- Recovery: coroutine robusta con backup/giro/detour/yield ----
    void TryRecovery() {
        if (isRecovering) return;
        StartCoroutine(RecoveryRoutine());
    }

    IEnumerator RecoveryRoutine() {
        isRecovering = true;
        int attempts = 0;

        while (attempts <= maxRecoveryRetries) {
            attempts++;
            Debug.Log($"{agentId} recovery sequence attempt {attempts}");

            // ---- Paso A: BACKUP corto (punto detrás)
            Vector3 backPoint = transform.position - transform.forward * backupDistance;
            NavMeshHit hit;
            if (NavMesh.SamplePosition(backPoint, out hit, 1.0f, NavMesh.AllAreas)) {
                Debug.Log($"{agentId} recovery: backup to {hit.position}");
                navMesh.SetDestination(hit.position);
                float t = 0f;
                while (t < backupTimeout) {
                    if (!navMesh.pathPending && navMesh.remainingDistance <= navMesh.stoppingDistance) break;
                    t += Time.deltaTime;
                    yield return null;
                }
                if (Vector3.Distance(transform.position, hit.position) > 0.05f) {
                    Debug.Log($"{agentId} recovery: backup successful");
                    isRecovering = false;
                    yield break;
                }
            }

            // ---- Paso B: pequeño giro lateral (prueba a la derecha e izquierda)
            Vector3 rightTrial = transform.position + transform.right * turnRadius;
            Vector3 leftTrial = transform.position - transform.right * turnRadius;
            bool moved = false;
            if (NavMesh.SamplePosition(rightTrial, out hit, 1.0f, NavMesh.AllAreas)) {
                Debug.Log($"{agentId} recovery: try turn-right to {hit.position}");
                navMesh.SetDestination(hit.position);
                float t = 0f;
                while (t < 0.7f) {
                    if (!navMesh.pathPending && navMesh.remainingDistance <= navMesh.stoppingDistance) break;
                    t += Time.deltaTime;
                    yield return null;
                }
                if (Vector3.Distance(transform.position, hit.position) > 0.05f) moved = true;
            }
            if (!moved && NavMesh.SamplePosition(leftTrial, out hit, 1.0f, NavMesh.AllAreas)) {
                Debug.Log($"{agentId} recovery: try turn-left to {hit.position}");
                navMesh.SetDestination(hit.position);
                float t = 0f;
                while (t < 0.7f) {
                    if (!navMesh.pathPending && navMesh.remainingDistance <= navMesh.stoppingDistance) break;
                    t += Time.deltaTime;
                    yield return null;
                }
                if (Vector3.Distance(transform.position, hit.position) > 0.05f) moved = true;
            }
            if (moved) {
                Debug.Log($"{agentId} recovery: lateral move successful");
                isRecovering = false;
                yield break;
            }

            // ---- Paso C: intentar detour aleatorio n veces
            for (int i = 0; i < detourAttempts; i++) {
                Vector3 rnd = transform.position + Random.insideUnitSphere * detourRadius;
                if (NavMesh.SamplePosition(rnd, out hit, detourRadius, NavMesh.AllAreas)) {
                    Debug.Log($"{agentId} recovery: detour attempt {i+1} -> {hit.position}");
                    navMesh.SetDestination(hit.position);
                    float t = 0f;
                    while (t < detourTimeoutPublic) {
                        if (!navMesh.pathPending && navMesh.remainingDistance <= navMesh.stoppingDistance) break;
                        t += Time.deltaTime;
                        yield return null;
                    }
                    if (Vector3.Distance(transform.position, hit.position) > 0.05f) {
                        Debug.Log($"{agentId} recovery: detour successful");
                        isRecovering = false;
                        yield break;
                    }
                }
                yield return null;
            }

            // ---- Paso D: si todo falla, hacer yield (ceder) unos instantes para que otros pasen
            Debug.Log($"{agentId} recovery: yielding for {yieldDuration} s to let others pass");
            if (navMesh != null) navMesh.isStopped = true;
            yield return new WaitForSeconds(yieldDuration + Random.Range(0f, 0.25f));
            if (navMesh != null) navMesh.isStopped = false;

            yield return null;
        }

        // Si finalmente no pudo salir, resetear path y esperar para replanear
        Debug.LogWarning($"{agentId} recovery: failed after {maxRecoveryRetries} attempts — ResetPath and pause");
        if (navMesh != null) {
            navMesh.ResetPath();
            navMesh.isStopped = true;
            yield return new WaitForSeconds(0.35f + Random.Range(0f, 0.25f));
            navMesh.isStopped = false;
        }
        isRecovering = false;
        yield break;
    }

    IEnumerator BriefYield() {
        // cede un momento (permite que otros agentes pasen)
        if (navMesh != null) navMesh.isStopped = true;
        yield return new WaitForSeconds(0.25f + Random.Range(0f, 0.3f));
        if (navMesh != null) navMesh.isStopped = false;
    }

    // Networking POSTs
    IEnumerator PostPickup(string agentIdStr, string boxObjName) {
        var url = "http://127.0.0.1:8000/pickup";
        var payload = new PickupPayload(agentIdStr, boxObjName);
        var json = JsonUtility.ToJson(payload);
        using (UnityWebRequest www = new UnityWebRequest(url, "POST")) {
            byte[] bodyRaw = System.Text.Encoding.UTF8.GetBytes(json);
            www.uploadHandler = new UploadHandlerRaw(bodyRaw);
            www.downloadHandler = new DownloadHandlerBuffer();
            www.SetRequestHeader("Content-Type", "application/json");
            yield return www.SendWebRequest();
            if (www.result != UnityWebRequest.Result.Success) {
                Debug.LogWarning("Pickup POST failed: " + www.error);
            } else {
                Debug.Log("Pickup POST OK: " + www.downloadHandler.text);
            }
        }
    }

    IEnumerator PostDrop(string agentIdStr, string boxObjName, Vector3 finalPos) {
        var url = "http://127.0.0.1:8000/drop";
        var payload = new DropPayload(agentIdStr, boxObjName, finalPos);
        var json = JsonUtility.ToJson(payload);
        using (UnityWebRequest www = new UnityWebRequest(url, "POST")) {
            byte[] bodyRaw = System.Text.Encoding.UTF8.GetBytes(json);
            www.uploadHandler = new UploadHandlerRaw(bodyRaw);
            www.downloadHandler = new DownloadHandlerBuffer();
            www.SetRequestHeader("Content-Type", "application/json");
            yield return www.SendWebRequest();
            if (www.result != UnityWebRequest.Result.Success) {
                Debug.LogWarning("Drop POST failed: " + www.error);
            } else {
                Debug.Log("Drop POST OK: " + www.downloadHandler.text);
            }
        }
    }

    // Payload classes
    [System.Serializable] public class PickupPayload { public string agent; public string box; public PickupPayload(string a, string b){ agent=a; box=b; } }
    [System.Serializable] public class DropPayload { public string agent; public string box; public Position position; public DropPayload(string a,string b,Vector3 p){ agent=a; box=b; position = new Position(p.x,p.y,p.z);} }
    [System.Serializable] public class Position { public float x,y,z; public Position(float X,float Y,float Z){ x=X; y=Y; z=Z; } }
}

using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;

public class CoordinatePoller : MonoBehaviour
{
    [Header("API")]
    public string apiUrl = "http://127.0.0.1:8000/coords";
    public float pollIntervalSeconds = 0.2f;

    [Header("Prefabs")]
    public GameObject agentPrefab;
    public GameObject boxPrefab;

    Dictionary<string, ObjectAgent> dynamicObjects = new Dictionary<string, ObjectAgent>();

    void OnEnable() {
        StartCoroutine(PollLoop());
    }

    IEnumerator PollLoop() {
        var wait = new WaitForSeconds(pollIntervalSeconds);
        while (true) {
            yield return StartCoroutine(FetchOnce());
            yield return wait;
        }
    }

    IEnumerator FetchOnce() {
        using (var req = UnityWebRequest.Get(apiUrl)) {
            yield return req.SendWebRequest();

            if (req.result != UnityWebRequest.Result.Success) {
                Debug.LogWarning("API error: " + req.error);
                yield break;
            }

            var json = req.downloadHandler.text;
            CoordsResponse payload = JsonUtility.FromJson<CoordsResponse>(json);
            if (payload?.objects == null) yield break;

            foreach (var obj in payload.objects) {
                if (string.IsNullOrEmpty(obj.id)) continue;

                if (!dynamicObjects.TryGetValue(obj.id, out var ag)) {
                    // Instanciar el prefab correspondiente
                    GameObject prefab = obj.id.StartsWith("Agent") ? agentPrefab : boxPrefab;
                    var go = Instantiate(prefab, Vector3.zero, Quaternion.identity);
                    go.name = obj.id;

                    var agentComp = go.GetComponent<UnityEngine.AI.NavMeshAgent>();
                    if (agentComp != null) {
                        agentComp.radius = 0.4f;
                        agentComp.speed = 2.8f;
                        agentComp.acceleration = 8f;
                        agentComp.angularSpeed = 120f;
                        agentComp.avoidancePriority = Random.Range(0, 99);
                    }

                    // Obtener el componente que ya trae el prefab
                    ag = go.GetComponent<ObjectAgent>();
                    if (ag == null) {
                        Debug.LogError($"El prefab {prefab.name} no tiene ObjectAgent adjunto.");
                        continue;
                    }

                    // Asignar dinámicamente el agentId
                    ag.agentId = obj.id;
                    Debug.Log($"Instanciado {go.name} (prefab: {prefab.name})");

                    // Guardar en el diccionario
                    dynamicObjects[obj.id] = ag;
                }

                // Actualizar posición
                Vector3 pos = obj.position.ToVector3();
                ag.SyncPosition(pos);
            }
        }
    }
}

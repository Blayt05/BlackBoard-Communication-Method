using System;
using UnityEngine;

[Serializable]
public class CoordsResponse {
    public long timestamp;
    public ObjectState[] objects;
}

[Serializable]
public class ObjectState {
    public string id;
    public Vec3 position;
    public Vec3 target;
    public float speed;
}

[Serializable]
public class Vec3 {
    public float x, y, z;
    public Vector3 ToVector3() {
        return new Vector3(x, y, z);
    }
}

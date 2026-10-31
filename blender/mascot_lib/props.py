"""Accessories: the phone is an independent object parented to the hand's prop socket."""
import numpy as np
import bpy
from mathutils import Matrix, Vector

from . import design as D


def phone_world_matrix(side=1):
    c, axes = D.RIG.phone_frame(side)
    M = Matrix.Identity(4)
    for i in range(3):
        M[i][0], M[i][1], M[i][2] = axes[0][i], axes[1][i], axes[2][i]
        M[i][3] = c[i]
    if side == -1:   # keep a right-handed basis on the mirrored side
        for i in range(3):
            M[i][0] = -M[i][0]
    return M


def attach_phone(rig, phone, side="L"):
    """Parent the phone to DEF_Prop.<side>. Moving or re-posing the socket bone
    moves the phone without touching the hand geometry."""
    phone.parent = rig
    phone.parent_type = "BONE"
    phone.parent_bone = f"DEF_Prop.{side}"
    bpy.context.view_layer.update()
    phone.matrix_world = rig.matrix_world @ phone_world_matrix(1 if side == "L" else -1)

"""A simple place to store game-wide constants!"""
import pymunk
from pymunk.vec2d import Vec2d

# Some screen initialization constants
SCREEN_SIZE = Vec2d(800, 600)
SCREEN_HALF = SCREEN_SIZE / 2

# Physics constants
SPACE = pymunk.Space()
# If we were using Python 3, we'd use an IntEnum
PLAYER_COLLISION_TYPE = 1
JUMP_THROUGH_COLLISION_TYPE = 2
BULLET_COLLISION_TYPE = 3
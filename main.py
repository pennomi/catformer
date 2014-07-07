"""Platformer demo in pygame/pymunk."""

import pygame
from pygame import locals as KEYS
from pygame.color import THECOLORS

import pymunk
import sys

from game import SCREEN_SIZE, SPACE
from game import (PLAYER_COLLISION_TYPE, JUMP_THROUGH_COLLISION_TYPE,
                  BULLET_COLLISION_TYPE)
from game.player import Player
from game.world import TileWorld


def jump_through_collision_handler(space, arbiter):
    # pass through only if going up
    return arbiter.shapes[0].body.velocity.y < 0


def bullet_collision_handler(space, arbiter):
    arbiter.shapes[0].body.player.health -= 1
    arbiter.shapes[1].body.bullet.destroy()
    return True


SPACE.gravity = (0, -1000)  # in px/sec^2
SPACE.add_collision_handler(
    PLAYER_COLLISION_TYPE, JUMP_THROUGH_COLLISION_TYPE,
    begin=jump_through_collision_handler)
SPACE.add_collision_handler(
    PLAYER_COLLISION_TYPE, BULLET_COLLISION_TYPE,
    begin=bullet_collision_handler)


def calculate_input(old_pressed_keys):
    # Manage all events
    for event in pygame.event.get():
        pressed_window_x = event.type == KEYS.QUIT
        pressed_esc = (event.type == KEYS.KEYDOWN and
                       event.key in [KEYS.K_ESCAPE])
        if pressed_window_x or pressed_esc:
            sys.exit()
    pressed = pygame.key.get_pressed()
    # increment all pressed keys
    for i, k in enumerate(pressed):
        if k:
            old_pressed_keys[i] = old_pressed_keys.get(i, 0) + 1
    # clear out any keys that are no longer pressed
    for k in list(old_pressed_keys.keys()):
        if not pressed[k]:
            del old_pressed_keys[k]
    return old_pressed_keys


def main():
    fps = 60
    dt = 1. / fps

    # Initialize the game
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=1, buffer=512)
    pygame.init()
    screen = pygame.display.set_mode((int(SCREEN_SIZE.x), int(SCREEN_SIZE.y)))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 16)

    # Music!
    pygame.mixer.music.load("res/music/fight.mp3")
    pygame.mixer.music.play(-1)  # loop forever

    # Load the world
    world = TileWorld('levels/level.tmx')
    player1 = Player("Player1", "res/images/cat1.png",
                     up=KEYS.K_UP, left=KEYS.K_LEFT,
                     right=KEYS.K_RIGHT, down=KEYS.K_DOWN, shoot=KEYS.K_SPACE)
    player2 = Player("Player2", "res/images/cat1.png",
                     up=KEYS.K_w, left=KEYS.K_a,
                     right=KEYS.K_d, down=KEYS.K_s, shoot=KEYS.K_e)
    players = [player1, player2]

    # track how long each key has been pressed
    pressed_keys = {}

    # Start the game loop
    running = True
    while running:
        # Input management
        pressed_keys = calculate_input(pressed_keys)

        # Update world
        SPACE.step(dt)
        world.update(dt, players)
        for player in players:
            player.update(pressed_keys)

        # Draw stuff
        screen.fill((54, 54, 54, 255))  # Dark gray color
        world.draw(screen)
        for player in players:
            player.draw(screen, world.camera)
        #pymunk.pygame_util.draw(screen, SPACE)  # TODO: camera support
        screen.blit(font.render("{} FPS".format(clock.get_fps()), 1,
                                THECOLORS["white"]), (0, 0))

        # Apply the drawing to the screen
        pygame.display.flip()

        # Wait for next frame
        clock.tick(fps)


if __name__ == '__main__':
    main()
"""Reworked platformer demo for pygame/pymunk.

Art from the good people at OpenGameArt.org

Cat Fighter sprites by dogchicken
http://opengameart.org/content/cat-fighter-sprite-sheet

Minimalist Tileset by Blarget2
http://opengameart.org/content/minimalist-pixel-tileset
"""

# TODO:
# * Rework animations entirely
# * Mirroring animations
# * Camera
# * Tiles and parallax loading from file
# * Shooting stuff

import json
import xml.etree.ElementTree as ET

import pygame
from pygame import locals as KEYS
from pygame.color import THECOLORS

import pymunk
from pymunk.vec2d import Vec2d
from pymunk.pygame_util import to_pygame


# Begin by initializing some constants for the physics world
PLAYER_COLLISION_TYPE = 1
JUMP_THROUGH_COLLISION_TYPE = 2


def jump_through_collision_handler(space, arbiter):
    # pass through only if going up
    return arbiter.shapes[0].body.velocity.y < 0

SPACE = pymunk.Space()
SPACE.gravity = (0, -1000)  # in px/sec^2
SPACE.add_collision_handler(
    PLAYER_COLLISION_TYPE, JUMP_THROUGH_COLLISION_TYPE,
    begin=jump_through_collision_handler)


class Player(object):
    def __init__(self, name, img, up=KEYS.K_UP, left=KEYS.K_LEFT,
                 right=KEYS.K_RIGHT, down=KEYS.K_DOWN):
        self.name = name

        # sprites
        self.frame_number = 0
        self.img = pygame.image.load(img)

        # sounds
        self.fall_sound = pygame.mixer.Sound("footstep05.ogg")

        # keybindings
        self.jump_key = up
        self.left_key = left
        self.right_key = right
        self.down_key = down

        # physics
        self.body = pymunk.Body(5, pymunk.inf)
        self.body.position = 100, 100

        # TODO: heads should be a separate collision type
        self.head = pymunk.Circle(self.body, 14, (12, 7))
        self.head.collision_type = PLAYER_COLLISION_TYPE
        self.head.friction = 0
        self.head.ignore_draw = True

        self.feet = pymunk.Circle(self.body, 14, (12, -16))
        self.feet.collision_type = 1
        # TODO: Make this zero whilst falling
        self.feet.friction = 2
        self.feet.ignore_draw = True

        SPACE.add(self.body, self.head, self.feet)

        # Character stats
        self.remaining_jumps = 2
        self.speed = 100
        self.jump_speed = 400
        self.health = 3

        # State tracking
        self.landed = False
        self.landing_speed = 0

        self.ground_velocity = Vec2d.zero()

    def update(self):
        self.ground_velocity = Vec2d.zero()
        self.landed = False

        # calculate useful local variables
        grounding = {}

        def get_grounding(arbiter):
            n = -arbiter.contacts[0].normal
            if n.y > 0:
                # only one of these ever gets this far
                self.ground_velocity = arbiter.shapes[1].body.velocity
                self.landed = True
                self.landing_speed = arbiter.total_impulse.y
                grounding['slope'] = n.x / n.y

        self.body.each_arbiter(get_grounding)

        if self.landed and grounding['slope'] < 2:
            self.remaining_jumps = 2

    def jump(self):
        if self.remaining_jumps:
            self.body.velocity.y = self.ground_velocity.y + self.jump_speed
            self.remaining_jumps -= 1

    def draw(self, screen):
        # play different animations depending on what's going on
        # TODO: These are all screwed up
        if self.landed and abs(self.ground_velocity.x) > 1:
            animation_offset = 128 * 0
        elif not self.landed:
            animation_offset = 128 * 1
        else:
            # walking animation
            animation_offset = 128 * (self.frame_number / 8 % 4)

        # match sprite to the physics object
        position = self.body.position + (-48, 76)

        # perform the actual draw
        screen.blit(self.img, to_pygame(position, screen),
                    (animation_offset, 128 * 0, 128, 128))

        # Did we land?
        if self.landing_speed / self.body.mass > 200:
            self.fall_sound.play()

        # Get ready for the next frame
        self.frame_number += 1

    def move(self, keys):
        target_vx = 0
        if keys.get(self.left_key):
            target_vx = -self.speed
        if keys.get(self.right_key):
            target_vx = self.speed
        self.feet.surface_velocity = (target_vx, 0)

        # Smooth Air control
        def lerp(f1, f2, d):
            """Interpolate from f1 to f2 by no more than d."""
            return f1 + min(max(f2 - f1, -d), d)

        if not self.landed:
            self.body.velocity.x = lerp(
                self.body.velocity.x, target_vx + self.ground_velocity.x, 10)

        # Terminal velocity
        self.body.velocity.y = max(self.body.velocity.y, -300)


class Tileset(object):
    def __init__(self, filename):
        self.img = pygame.image.load(filename)
        self.tile_width = 32
        self.tile_height = 32

    def draw(self, screen, tile_id, position):
        if not tile_id:
            return  # There was nothing to be drawn
        tile_id -= 1  # we're 1-indexed in Tiled
        tiles_wide = self.img.get_width() // self.tile_width
        source_x = (tile_id % tiles_wide) * self.tile_width
        source_y = (tile_id // tiles_wide) * self.tile_height
        screen.blit(self.img, to_pygame(position, screen),
                    (source_x, source_y, self.tile_width, self.tile_height))


class World(object):
    def __init__(self, filename):
        # Load the Tileset
        self.tileset = Tileset('mininicular.png')

        # Parse the TMX
        self.tree = ET.parse(filename)
        root = self.tree.getroot()
        for layer in root.findall('layer'):
            # This is the csv of the map data
            csv = layer.findall('data')[0].text
            self.data = [row for row in csv.split('\n')]
            self.data.reverse()  # pygame is opposite of Tiled
        map_height = 32 * 50  # TODO: hardcoded
        # These are the collision objects
        for object_group in root.findall('objectgroup'):
            for obj in object_group.iter('object'):
                jump_through = False
                for p in obj.iter('property'):
                    if p.get('name') == "jump_through":
                        jump_through = True
                line = obj.find('polyline')
                group_x = int(obj.get('x'))
                group_y = int(obj.get('y'))
                point_strings = line.get('points').split()
                point_strings = [p.split(',') for p in point_strings]
                point_strings = [(group_x + int(p[0]), map_height-group_y-int(p[1])) for p in point_strings]
                print(point_strings)
                Platform(point_strings, jump_through=jump_through)

    def draw(self, screen):
        screen_h = screen.get_height() + 32
        screen_w = screen.get_width() + 32
        # TODO: only iterate over what'll fit on the screen
        # (We'll implement this *after* the camera)
        for y, row in enumerate(self.data):
            for x, tile_id in enumerate(row.split(',')):
                if tile_id == '':
                    continue
                if x*32 > screen_w:
                    continue
                if y*32 > screen_h:
                    continue
                self.tileset.draw(screen, int(tile_id), (x*32, y*32))


class Platform(object):
    def __init__(self, points, jump_through=False):
        is_moving = False  # bool(path.get("positions"))
        # Create the body type
        if is_moving:
            self.body = pymunk.Body(pymunk.inf, pymunk.inf)
        else:
            self.body = SPACE.static_body
        # Keep track of moving platforms
        for i in xrange(len(points)-1):
            # Make and configure the physics object
            seg = pymunk.Segment(self.body, points[i], points[i+1], 5)
            seg.friction = 1
            seg.group = 1
            if jump_through:
                seg.collision_type = JUMP_THROUGH_COLLISION_TYPE
                seg.color = (255, 255, 0, 255)
            if is_moving:
                seg.color = THECOLORS["blue"]
                seg.body.position = Vec2d(path["positions"][0])
            # Add it to the world
            SPACE.add(seg)

        # Moving platforms need to be operated on later
        if is_moving:
            plat = MovingPlatform(self.body, path["positions"],
                                  path.get("speed", 1))
            moving_platforms.append(plat)


class MovingPlatform(object):
    def __init__(self, body, positions, speed):
        self.body = body
        self.positions = positions
        self.speed = speed

        # Keep track of the active point
        self.target_index = 0

    def update(self, dt):
        destination = self.positions[self.target_index]
        current_pos = Vec2d(self.body.position)
        distance = current_pos.get_distance(destination)
        if distance < self.speed:
            self.target_index = (self.target_index + 1) % len(self.positions)
            t = 1
        else:
            t = self.speed / distance
        new_pos = current_pos.interpolate_to(destination, t)
        self.body.position = new_pos
        self.body.velocity = (new_pos - current_pos) / dt


def main():
    fps = 60
    dt = 1. / fps

    # Initialize the game
    pygame.mixer.pre_init(44100, -16, 1, 512)  # adjusts for sound lag
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()
    running = True
    font = pygame.font.SysFont("Arial", 16)

    # Generate the visible world
    world = World('level.tmx')

    # Generate the physics world
    moving_platforms = []

    with open("level.json", 'r') as infile:
        level = json.load(infile)

    for path in level["paths"]:
        points = path["points"]
        is_moving = bool(path.get("positions"))
        is_jump_through = bool(path.get("jump_through"))
        # Create the body type
        if is_moving:
            body = pymunk.Body(pymunk.inf, pymunk.inf)
        else:
            body = SPACE.static_body
        # Keep track of moving platforms
        for i in xrange(len(points)-1):
            # Make and configure the physics object
            seg = pymunk.Segment(body, points[i], points[i+1], 5)
            seg.friction = 1
            seg.group = 1
            if is_jump_through:
                seg.collision_type = JUMP_THROUGH_COLLISION_TYPE
                seg.color = (255, 255, 0, 255)
            if is_moving:
                seg.color = THECOLORS["blue"]
                seg.body.position = Vec2d(path["positions"][0])
            # Add it to the world
            SPACE.add(seg)

        # Moving platforms need to be operated on later
        if is_moving:
            plat = MovingPlatform(body, path["positions"],
                                  path.get("speed", 1))
            moving_platforms.append(plat)

    # player
    player1 = Player("Player1", "cat1.png",
                     up=KEYS.K_UP, left=KEYS.K_LEFT,
                     right=KEYS.K_RIGHT, down=KEYS.K_DOWN)
    player2 = Player("Player2", "cat1.png",
                     up=KEYS.K_w, left=KEYS.K_a, right=KEYS.K_d, down=KEYS.K_s)
    players = [player1, player2]

    # track how long each key has been pressed
    pressed_keys = {}

    # Start the game loop
    while running:
        # Input management
        # Manage all events
        events = pygame.event.get()
        for event in events:
            pressed_window_x = event.type == KEYS.QUIT
            pressed_esc = (event.type == KEYS.KEYDOWN and
                           event.key in [KEYS.K_ESCAPE])
            if pressed_window_x or pressed_esc:
                running = False  # exit the program
        pressed = pygame.key.get_pressed()
        # increment all pressed keys
        for i, k in enumerate(pressed):
            if k:
                pressed_keys[i] = pressed_keys.get(i, 0) + 1
        # clear out any keys that are no longer pressed
        for k in pressed_keys.keys():
            if not pressed[k]:
                del pressed_keys[k]

        # Update physics
        SPACE.step(dt)

        # Update players
        for player in players:
            player.update()
        for player in players:
            if pressed_keys.get(player.jump_key) == 1:
                player.jump()
        for player in players:
            player.move(pressed_keys)

        # Move the moving platforms
        for platform in moving_platforms:
            platform.update(dt)

        # Draw stuff
        # Clear screen
        screen.fill((109, 169, 101, 255))  # Light green color
        # Draw tiles
        world.draw(screen)
        # Draw players
        for player in players:
            player.draw(screen)
        # Debug draw physics
        pymunk.pygame_util.draw(screen, SPACE)
        # Draw fps label
        screen.blit(font.render("{} FPS".format(clock.get_fps()), 1,
                                THECOLORS["white"]), (0, 0))
        # Apply the drawing to the screen
        pygame.display.flip()

        # Wait for next frame
        clock.tick(fps)


if __name__ == '__main__':
    main()
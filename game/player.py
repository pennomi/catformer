"""This module contains the entities controlled by the player."""
import pygame
import weakref
from pymunk import Vec2d
import pymunk
from pymunk.pygame_util import to_pygame
from game import BULLET_COLLISION_TYPE, SPACE, SCREEN_HALF, \
    PLAYER_COLLISION_TYPE


def _bullet_velocity_func(body, gravity, damping, dt):
    return body.velocity


class Bullet(object):
    def __init__(self, owner, gravity=False):
        self.radius = 3
        self.speed = 500
        self.ttl = 40
        self.cooldown = 10

        self.shot_sound = pygame.mixer.Sound("res/sfx/C_28P.ogg")
        self.shot_sound.play()

        facing_left = owner.current_facing == owner.left_key
        vel = Vec2d(-self.speed, 0) if facing_left else Vec2d(self.speed, 0)
        offset = Vec2d(0, 0) if facing_left else Vec2d(20, 0)
        self.body = pymunk.Body(1, pymunk.inf)
        self.body.position = owner.body.position + offset
        self.body.velocity = owner.body.velocity + vel
        self.body.bullet = weakref.proxy(self)
        if not gravity:
            self.body.velocity_func = _bullet_velocity_func
        self.shape = pymunk.Circle(self.body, self.radius, (0, 0))
        self.shape.collision_type = BULLET_COLLISION_TYPE
        self.shape.friction = 0
        SPACE.add(self.body, self.shape)
        self.active = True

    def update(self):
        self.ttl -= 1
        if self.ttl < 0:
            self.destroy()
        return self.active

    def destroy(self):
        try:
            SPACE.remove(self.body, self.shape)
            self.active = False
        except KeyError:
            pass

    def draw(self, screen, camera):
        if not self.active:
            return
        position = to_pygame(self.body.position - camera + SCREEN_HALF, screen)
        pygame.draw.circle(screen, (0, 0, 0, 0), position, self.radius)


class Animation(object):
    def __init__(self, images, row, frame_count,
                 start_frame=0, loop=False, frame_rate=.15):
        self.img, self.flip_img = images
        self.row = row
        self.frame_count = frame_count
        self.start_frame = start_frame
        self.loop = loop
        self.frame_rate = frame_rate
        self.current_frame = 0
        self.done = False

    def draw(self, screen, pos, flip):
        # center the sprite
        position = pos - Vec2d(48, 76)

        # get the portion we should draw
        frame = int(self.current_frame)
        self.current_frame += self.frame_rate
        if self.current_frame >= self.frame_count:
            if self.loop:
                self.current_frame = 0
            else:
                self.current_frame -= self.frame_rate  # stick on the last frame
                self.done = True

        img = self.flip_img if flip else self.img
        # TODO: remove hardcoded sprite size
        sprite_size = 128
        x = (frame + self.start_frame) * sprite_size
        if flip:
            x = img.get_width() - x - sprite_size
        y = self.row * sprite_size
        screen.blit(img, position, (x, y, sprite_size, sprite_size))


class Player(object):
    def __init__(self, name, img, up=None, left=None,
                 right=None, down=None, shoot=None):
        self.name = name

        # sprites
        img = pygame.image.load(img)
        flip_img = pygame.transform.flip(img, True, False)
        images = (img, flip_img)

        # animations
        self.idle_loop = Animation(images, 0, 4, loop=True)
        self.walk_loop = Animation(images, 1, 8, loop=True)
        self.jump_loop = Animation(images, 2, 2, start_frame=2, loop=True)
        self.spin_loop = Animation(
            images, 3, 4, start_frame=3, loop=True, frame_rate=0.4)
        self.death_sequence = Animation(images, 4, 7)

        # sounds
        self.fall_sound = pygame.mixer.Sound("res/sfx/fall.wav")
        self.fall_sound.set_volume(0.5)
        self.jump_sound = pygame.mixer.Sound("res/sfx/jump.wav")
        self.jump_sound.set_volume(0.5)

        # keybindings
        self.jump_key = up
        self.left_key = left
        self.right_key = right
        self.down_key = down
        self.shoot_key = shoot

        # physics
        self.body = pymunk.Body(5, pymunk.inf)  # mass, moment
        self.body.position = 100, 100
        self.body.player = weakref.proxy(self)

        # TODO: heads should be a separate collision type
        self.head = pymunk.Circle(self.body, 14, (12, 7))
        self.head.collision_type = PLAYER_COLLISION_TYPE
        self.head.friction = 0

        self.feet = pymunk.Circle(self.body, 14, (12, -16))
        self.feet.collision_type = 1
        # TODO: Make this zero whilst falling
        self.feet.friction = 2

        SPACE.add(self.body, self.head, self.feet)

        # Character stats
        self.max_jumps = 2
        self.remaining_jumps = self.max_jumps
        self.speed = 100
        self.jump_speed = 400
        self.max_health = 10
        self.health = self.max_health
        self.shot_cooldown = 0

        # State tracking
        self.landed = False
        self.landed_hard = False
        self.ground_velocity = Vec2d.zero()
        self.ground_slope = 0
        self.current_facing = self.right_key
        self.bullets = []

    def update(self, pressed_keys):
        for b in self.bullets[:]:  # iterate over a copy
            if not b.update():
                self.bullets.remove(b)

        # Tick the cooldown
        if self.shot_cooldown:
            self.shot_cooldown -= 1
        self.landed = False
        self.landed_hard = False

        def calculate_landing(arbiter):
            n = -arbiter.contacts[0].normal
            shape = arbiter.shapes[1]
            if n.y > 0 and shape.collision_type != BULLET_COLLISION_TYPE:
                # wrap in Vec2d to copy the vector
                v = Vec2d(shape.body.velocity)
                self.ground_velocity = v
                self.landed = True
                # 100 is landed, 1000 is "being squished"
                landing_speed = arbiter.total_impulse.y / self.body.mass
                self.landed_hard = landing_speed > 100
                if landing_speed > 1000:
                    self.health -= 1
                self.ground_slope = n.x / n.y
        self.body.each_arbiter(calculate_landing)

        if self.health < 0:
            return  # No moving around for you!

        if self.landed and self.ground_slope < 2:
            self.remaining_jumps = self.max_jumps

        # Jump
        if pressed_keys.get(self.jump_key) == 1:
            self.jump()

        # Move
        self.move(pressed_keys)

        if pressed_keys.get(self.shoot_key):
            self.shoot()

    def shoot(self):
        if self.shot_cooldown:
            return
        bullet = Bullet(self)
        self.bullets.append(bullet)
        self.shot_cooldown = bullet.cooldown

    def jump(self):
        if self.remaining_jumps:
            self.jump_sound.play()
            self.body.velocity.y = self.ground_velocity.y + self.jump_speed
            self.remaining_jumps -= 1

    def draw(self, screen, camera):
        # match sprite to the physics object
        position = self.body.position - camera + SCREEN_HALF
        position = Vec2d(to_pygame(position, screen))

        # play different animations depending on what's going on
        # TODO: These are all screwed up
        flip = self.current_facing == self.left_key

        if self.health < 0:
            self.death_sequence.draw(screen, position, flip)
        elif self.landed and abs(self.feet.surface_velocity.x) > 1:
            # walking
            self.walk_loop.draw(screen, position, flip)
        elif self.landed:
            # idle
            self.idle_loop.draw(screen, position, flip)
        elif self.remaining_jumps > 0:
            # falling
            self.jump_loop.draw(screen, position, flip)
        elif self.remaining_jumps == 0:
            # spinning
            self.spin_loop.draw(screen, position, flip)
        else:
            # I dunno what else to do
            self.idle_loop.draw(screen, position, flip)

        # Draw health bar
        health_percent = max(float(self.health) / self.max_health, 0)
        if health_percent:
            rect = (position.x, position.y - 35, 30 * health_percent, 5)
            pygame.draw.rect(screen, (255, 0, 0, 0), rect)

        # Did we land?
        if self.landed_hard:
            self.fall_sound.play()

        # Draw our bullets
        for bullet in self.bullets:
            bullet.draw(screen, camera)

    def move(self, keys):
        target_vx = 0
        if keys.get(self.left_key):
            self.current_facing = self.left_key
            target_vx = -self.speed
        if keys.get(self.right_key):
            self.current_facing = self.right_key
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

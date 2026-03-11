import docker

IP = '0.0.0.0'
PORT = '5000'
img_tag = 'test-img'
container_name = 'test-container'
client = docker.from_env(timeout=86400)


def stop():
    container = client.containers.get(container_name)
    container.stop()
    print('Container stopped.')


def rm_container():
    container = client.containers.get(container_name)
    container.remove()
    print('Container removed.')


def rm_img():
    client.images.remove(img_tag)
    print('Image removed.')


if __name__ == '__main__':
    stop()
    rm_container()
    rm_img()

import argparse

def main():
    p = argparse.ArgumentParser(description='MeshShield local USB dashboard')
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--simulate', action='store_true')
    mode.add_argument('--port', help='Explicit Argon port, e.g. COM7')
    p.add_argument('--list-ports', action='store_true')
    p.add_argument('--http-port', type=int, default=8000)
    p.add_argument('--z-threshold', type=float, default=3.0)
    a = p.parse_args()
    if a.list_ports:
        from serial.tools import list_ports
        for port in list_ports.comports():
            print(f'{port.device}\t{port.description}\t{port.hwid}')
        return
    if not a.simulate and not a.port:
        p.error('Select --simulate or --port COM_NUMBER')
    if not 1 <= a.z_threshold <= 10:
        p.error('--z-threshold must be 1–10')
    import uvicorn
    from .app import create_app
    uvicorn.run(create_app(simulate=a.simulate, port=a.port, z=a.z_threshold),
                host='127.0.0.1', port=a.http_port, workers=1, reload=False)

if __name__ == '__main__':
    main()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_port: int = 8100
    wms_api_base_url: str = "http://192.168.68.41"
    wms_device_id: str = "pi-fingerprint-01"
    wms_device_secret: str = "change_me"
    fingerprint_serial_port: str = "/dev/ttyUSB0"
    fingerprint_baud_rate: int = 57600
    fingerprint_sensor_address: int = 0xFFFFFFFF
    fingerprint_sensor_password: int = 0x00000000
    fingerprint_read_timeout_seconds: int = 15
    fingerprint_poll_interval_seconds: float = 0.02
    search_include_image: bool = False
    wms_events_endpoint: str = "/api/biometric/events"
    send_events_to_wms: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def wms_events_url(self) -> str:
        return self.wms_api_base_url.rstrip("/") + self.wms_events_endpoint


settings = Settings()

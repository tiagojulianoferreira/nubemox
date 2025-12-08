class StorageManager:
    """Mixin para operações de Storage."""

    def get_storages(self, node_id=None):
        return {'data': self.connection.storage.get()}

    def get_storage_content(self, storage_id, node_id=None):
        node_id = self._resolve_node_id(node_id)
        content = self.connection.nodes(node_id).storage(storage_id).content.get()
        return {'data': content}
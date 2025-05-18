DROP TRIGGER IF EXISTS tgr_update_updated_at_column ON admin_user;
                CREATE TRIGGER tgr_update_updated_at_column
                BEFORE UPDATE ON admin_user
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();